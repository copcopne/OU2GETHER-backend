from rest_framework import viewsets, generics, status, parsers, permissions
from rest_framework.decorators import action
from cloudinary.uploader import upload
from rest_framework.response import Response
from ou2gether import models
from ou2gether import serializers, perms, paginators
from django.utils.dateparse import parse_datetime
import json
from django.utils import timezone
from django.http import JsonResponse
from django.utils.timezone import make_aware
from datetime import datetime
from django.core.mail import send_mail


def _handle_media_upload(files, comment_obj=None, post_obj=None):
    for file in files:
        media_type = 'image' if file.content_type.startswith('image/') else 'video'
        upload_result = upload(file, resource_type=media_type)
        path = f"{upload_result['resource_type']}/upload/v{upload_result['version']}/{upload_result['public_id']}.{upload_result['format']}"
        if comment_obj:
            models.CommentMedia.objects.create(
                comment=comment_obj,
                file=path,
                media_type=media_type
            )
            comment_obj.refresh_from_db()
        else:
            models.PostMedia.objects.create(
                post=post_obj,
                file=path,
                media_type=media_type
            )
            post_obj.refresh_from_db()


def _handle_interact(request, target_obj, reaction, is_post=True):
    reaction = reaction.upper()

    try:
        reaction_value = models.InteractionChoices[reaction]
    except KeyError:
        return Response({'detail': 'Invalid interaction.'}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    filter_kwargs = {'user': user}
    filter_kwargs['post' if is_post else 'comment'] = target_obj

    existing = models.Interaction.objects.filter(**filter_kwargs).first()

    if existing:
        if existing.type == reaction_value and existing.is_active:
            existing.is_active = False
            existing.save()
            return Response({'detail': 'Remove interaction successfully.'}, status=status.HTTP_200_OK)
        else:
            existing.type = reaction_value
            existing.is_active = True
            existing.save()
            return Response(serializers.InteractionListSerializer(existing).data, status=status.HTTP_200_OK)

    serializer = serializers.InteractionCreateSerializer(
        data={'type': reaction_value},
        context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    kwargs = {'post': target_obj} if is_post else {'comment': target_obj}
    interaction = serializer.save(**kwargs)

    return Response(serializers.InteractionListSerializer(interaction).data, status=status.HTTP_201_CREATED)


def _get_followers_or_following(user, is_follower=True):
    if is_follower:
        follows = models.Follow.objects.filter(following=user, is_active=True)
        user_ids = follows.values_list('follower_id', flat=True)
    else:
        # mình đang follow ai?
        follows = models.Follow.objects.filter(follower=user, is_active=True)
        user_ids = follows.values_list('following_id', flat=True)

    return models.User.objects.filter(id__in=user_ids, is_active=True)


class UserViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = models.User.objects.filter(is_active=True)
    serializer_class = serializers.UserSerializer
    permission_classes = [perms.IsNotRestricted]
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]
    pagination_class = paginators.UserPagination

    def get_queryset(self):
        queryset =  super().get_queryset()
        params = self.request.query_params

        keyword = params.get('kw')
        if keyword:
            queryset = queryset.filter(Q(first_name__icontains=keyword) | Q(last_name__icontains=keyword))
        return queryset
    
    def get_permissions(self):
        if self.action == 'retrieve':
            return [perms.IsNotRestricted()]
        return super().get_permissions()
    
    def retrieve(self, request, pk):
        user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        self.check_object_permissions(request, user)
        serializer = serializers.UserSerializer(user, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='register', permission_classes=[permissions.AllowAny])
    def register(self, request):
        user_data = request.data.copy()
        user_data['is_active'] = True
        user_data['is_verified'] = False

        if 'role' not in user_data:
            user_data['role'] = models.Role.STUDENT

        current_user = request.user
        if current_user.is_authenticated:
            if current_user.role == models.Role.ADMIN and int(user_data.get('role', 2)) == models.Role.LECTURER:
                user_data['password'] = 'ou@123'
                user_data['must_change_password'] = True
                user_data['set_password_deadline'] = timezone.now() + timezone.timedelta(hours=24)
            else:
                return Response({'detail': 'You do not have permission to create this user.'}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = serializers.UserSerializer(data=user_data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(serializers.UserSerializer(user, context={'request': request}).data, 
                        status=status.HTTP_201_CREATED)

    @action(methods=['get', 'patch'], url_path='current-user', detail=False, permission_classes=[permissions.IsAuthenticated])
    def get_current_user(self, request):
        u = request.user

        if request.method == 'PATCH':
            for k, v in request.data.items():
                if k == 'password':
                    u.set_password(v)
                elif k in ['avatar', 'cover', 'first_name', 'last_name', 'bio', 'email']:
                    setattr(u, k, v)
            u.save()

        return Response(serializers.UserSerializer(u, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='block-user',permission_classes=[perms.IsNotRestricted])
    def block_user(self, request, pk):
        target_user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        if request.user == target_user:
            return Response({'detail': 'Cannot block yourself.'}, status=status.HTTP_400_BAD_REQUEST)

        models.Block.objects.create(user=request.user, blocked_user=target_user)
        return Response({'detail': 'User blocked successfully.'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='unblock-user',permission_classes=[permissions.IsAuthenticated])
    def unblock_user(self, request, pk):
        target_user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        if request.user == target_user:
            return Response({'detail': 'Cannot unblock yourself.'}, status=status.HTTP_400_BAD_REQUEST)

        models.Block.objects.filter(user=request.user, blocked_user=target_user).delete()
        return Response({'detail': 'User unblocked successfully.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def follow(self, request, pk):
        user_to_follow = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        user_who_follow = request.user

        follow_obj = user_who_follow.followings.filter(following=user_to_follow).first()

        if follow_obj:
            follow_obj.is_active = not follow_obj.is_active
            follow_obj.save()
        else:
            models.Follow.objects.create(follower=user_who_follow, following=user_to_follow)

        serializer = self.get_serializer(user_to_follow, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def followers(self, request, pk):
        user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        followers_qs = _get_followers_or_following(user, is_follower=True)

        page = self.paginate_queryset(followers_qs)
        if page is not None:
            serializer = serializers.MinimalUserSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.MinimalUserSerializer(followers_qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def following(self, request, pk):
        user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        following_qs = _get_followers_or_following(user, is_follower=False)

        page = self.paginate_queryset(following_qs)
        if page is not None:
            serializer = serializers.MinimalUserSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = serializers.MinimalUserSerializer(following_qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='unverified-users',permission_classes=[permissions.IsAdminUser])
    def unverified_users(self, request):
        unverified_users = models.User.objects.filter(is_verified=False, is_active=True)
        page = self.paginate_queryset(unverified_users)

        if page is not None:
            serializer = serializers.UserSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = serializers.UserSerializer(unverified_users, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def verify(self, request, pk):
        user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        if user.is_verified:
            return Response({'detail': 'User is already verified.'}, status=status.HTTP_400_BAD_REQUEST)

        user.is_verified = True
        user.save()
        send_mail(
            'Thông báo tình trạng tài khoản',
            'Chào bạn,\nTài khoản của bạn đã được xác nhận và đã có thể truy cập vào hệ thống.\nChúc bạn có trải nghiệm tốt.',
            'copcopne@gmail.com',
            [user.email],
            fail_silently=False,
        )
        return Response({'detail': 'User verified successfully.'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='reset-password-deadline', permission_classes=[permissions.IsAdminUser])
    def reset_password_deadline(self, request, pk):
        user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        if user.role != models.Role.LECTURER or user.must_change_password != True or user.is_locked != True:
            return Response({'detail': "User does not need to reset password deadline."}, status=status.HTTP_400_BAD_REQUEST)

        user.must_change_password = True
        user.is_locked = False
        user.reset_password_deadline = timezone.now() + timezone.timedelta(days=1)
        user.save()
        return Response({'detail': 'Password reset deadline set successfully.'}, status=status.HTTP_200_OK)

class PostViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = models.Post.objects.filter(is_active=True)
    serializer_class = serializers.PostSerializer
    permission_classes = [perms.IsNotRestricted]
    pagination_class = paginators.PostPagination
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get('userId'):
            user_id = params.get('userId')
            queryset = queryset.filter(author__id=user_id)
        if params.get('poll'):
            queryset = queryset.filter(post_type=models.PostType.POLL)
        if params.get('following'):
            followed_user_ids = models.Follow.objects.filter(follower=self.request.user).values_list('following_id', flat=True)
            queryset = queryset.filter(author__in=followed_user_ids)

        return queryset

    def get_permissions(self):
        if self.action == 'retrieve':
            return [perms.IsNotRestricted()]
        return super().get_permissions()
    
    def retrieve(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        self.check_object_permissions(request, post)
        serializer = serializers.PostSerializer(post, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        post_data = request.data.copy()
        files = request.FILES.getlist('media')
        has_poll = bool(post_data.get('poll'))
        has_media = bool(files)

        if has_poll and has_media:
            return Response(
                {'detail': 'Cannot create a post with both poll and media.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        poll_data = None
        if has_poll:
            try:
                poll_data = json.loads(post_data.pop('poll')[0])
            except json.JSONDecodeError:
                return Response({'detail': 'Invalid poll JSON.'}, status=status.HTTP_400_BAD_REQUEST)

            raw_end_time = poll_data.get('end_time')
            if not raw_end_time:
                return Response({'detail': 'Poll end_time is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            dt = parse_datetime(raw_end_time)
            if not dt:
                return Response({'detail': 'end_time must be ISO datetime string.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())

            if dt < timezone.now():
                return Response({'detail': 'Poll end time must be in the future.'},
                                status=status.HTTP_400_BAD_REQUEST)

            poll_data['end_time'] = dt

        post_data['author'] = request.user.id
        if poll_data:
            t = models.PostType.POLL
        elif has_media:
            t = models.PostType.MEDIA
        else:
            t = models.PostType.TEXT

        serializer = self.get_serializer(data=post_data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        post = serializer.save(author=request.user, post_type=t)

        if has_media:
            _handle_media_upload(files, post_obj=post)

        if poll_data:
            poll_data['post'] = post.id
            poll_serializer = serializers.PostPollSerializer(data=poll_data)
            poll_serializer.is_valid(raise_exception=True)
            poll = poll_serializer.save()
            post.poll = poll
            post.save()

            # for opt in poll_data.get('options', []):
            #     opt_serializer = serializers.PollOptionSerializer(data=opt)
            #     opt_serializer.is_valid(raise_exception=True)
            #     opt_serializer.save(post_poll=poll)

        return Response(serializers.PostSerializer(post, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='update-post', permission_classes=[perms.PostOwner])
    def update_post(self, request, pk):

        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to edit this post."}, status=status.HTTP_403_FORBIDDEN)
        
        is_edited = False
        for k, v in request.data.items():
            if k =='poll':
                try:
                    poll_data = json.loads(v)
                    if poll_data.get('end_time'):
                        poll_data['end_time'] = timezone.datetime.fromisoformat(poll_data['end_time'])
                        if timezone.is_naive(poll_data['end_time']):
                            poll_data['end_time'] = timezone.make_aware(poll_data['end_time'], timezone.get_current_timezone())

                        if poll_data['end_time'] < timezone.now():
                            return Response({'detail': 'Poll end time must be in the future.'}, status=status.HTTP_400_BAD_REQUEST)
                        
                    serializer = serializers.PostPollSerializer(instance=post.poll, data=poll_data, partial=True)
                    serializer.is_valid(raise_exception=True)
                    serializer.save()
                    is_edited = True
                except json.JSONDecodeError:
                    return Response({'detail': 'Invalid poll JSON.'}, status=status.HTTP_400_BAD_REQUEST)
            elif k == 'content':
                if not v.strip():
                    return Response({'detail': 'Content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
                post.content = v
                is_edited = True

            elif k == 'is_commendable':
                post.is_commendable = v
                is_edited = True

        if is_edited:
            post.is_edited = True
            post.save()
            return Response(self.get_serializer(post, context={'request': request}).data, status=status.HTTP_200_OK)
        
        return Response({"detail":"No changes were made."}, status=status.HTTP_400_BAD_REQUEST)

    
    @action(detail=True, methods=['post'], url_path='update-post/upload-media', permission_classes=[perms.PostOwner])
    def upload_media(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to edit this post."}, 
                            status=status.HTTP_403_FORBIDDEN)
        
        if post.post_type != models.PostType.MEDIA:
            return Response({"detail":"This post is not a media post."}, 
                            status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, post_obj=post)
        
        post.is_edited = True
        post.save()
        post.refresh_from_db()

        return Response(self.get_serializer(post, context={'request': request}).data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['delete'], url_path=r'update-post/media/(?P<media_id>\d+)', permission_classes=[perms.PostOwner])
    def delete_media(self, request, pk, media_id):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to edit this post."}, 
                            status=status.HTTP_403_FORBIDDEN)
    
        if post.post_type != models.PostType.MEDIA:
            return Response({"detail":"This post is not a media post."}, 
                            status=status.HTTP_400_BAD_REQUEST)

        media = generics.get_object_or_404(models.PostMedia, pk=media_id, post=post, is_active=True)
        if media.is_active == False:
            return Response({"detail":"This media has already been deleted."}, 
                            status=status.HTTP_400_BAD_REQUEST)
        
        media.is_active = False
        media.save()
        media.refresh_from_db()

        post.is_edited = True
        post.save()
        post.refresh_from_db()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def share(self, request, pk):
        print(timezone.localtime(timezone.now()))
        shared_post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        
        while shared_post.is_shared and shared_post.shared_post:
            shared_post = shared_post.shared_post

        if request.data.get('media') or request.data.get('poll'):
            return Response(
                {'detail': 'Cannot create a shared post with media or poll.'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)


        share = serializer.save(
            author=request.user,
            post_type=models.PostType.TEXT,
            is_shared=True,
            shared_post=shared_post
        )

        return Response(serializers.PostSerializer(share, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='delete-post',permission_classes=[perms.CanDeletePost])
    def delete_post(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to delete this post."}, status=status.HTTP_403_FORBIDDEN)
        
        post.is_active = False
        post.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def comments(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        comments = models.Comment.objects.filter(post=post, is_active=True)

        page = self.paginate_queryset(comments)
        if page is not None:
            serializer = serializers.CommentSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = serializers.CommentSerializer(comments, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def comment(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        comment_data = request.data.copy()
        comment_data['post'] = post.id
        comment_data['author'] = request.user.id

        if(not comment_data.get('content').strip()):
            return Response({'detail': 'Content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = serializers.CommentSerializer(data=comment_data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(author=request.user)

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, comment_obj=comment)

        return Response(serializers.CommentSerializer(comment).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def interactions(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        interactions = models.Interaction.objects.filter(post=post, is_active=True)

        page = self.paginate_queryset(interactions)
        if page is not None:
            serializer = serializers.InteractionListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.InteractionListSerializer(interactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


    @action(detail=True, methods=['post'], url_path=r'interact/(?P<reaction>\w+)', permission_classes=[perms.IsNotRestricted])
    def interact(self, request, pk, reaction=None):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        return _handle_interact(request, post, reaction, is_post=True)
    
    @action(detail=True, methods=['post'], url_path='vote', permission_classes=[perms.IsNotRestricted])
    def vote(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        if post.post_type != models.PostType.POLL:
            return Response({"detail":"This post is not a poll."}, status=status.HTTP_400_BAD_REQUEST)
        
        option_ids = request.data.get('option_ids', [])
        if not isinstance(option_ids, list):
            return Response({"detail": "option_ids must be a list object."}, status=status.HTTP_400_BAD_REQUEST)
        
        for oid in option_ids:
            option = generics.get_object_or_404(models.PollOption, pk=oid, post_poll=post.poll)
            vote_qs = models.PollVote.objects.filter(user=request.user, poll_option=option)
            if vote_qs.exists():
                vote_qs.delete()
            else:
                models.PollVote.objects.create(user=request.user, poll_option=option)
            
        return Response(self.get_serializer(post, context={'request': request}).data, 
                        status=status.HTTP_200_OK)


class CommentViewSet(viewsets.ViewSet):
    queryset = models.Comment.objects.filter(is_active=True)
    serializer_class = serializers.CommentSerializer
    permission_classes = [perms.IsAuthenticated]
    pagination_class = paginators.CommentPagination

    @action(detail=True, methods=['patch'], url_path='update-comment', permission_classes=[perms.CommentOwner])
    def update_comment(self, request, pk):
        comment = generics.get_object_or_404(models.Comment, pk=pk, is_active=True)
        
        comment.is_edited = True
        content = request.data.get('content')
        if content:
            comment.content = content
        comment.save()

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, comment_obj=comment)

        return Response(serializers.CommentSerializer(comment).data)

    @action(detail=True, methods=['delete'], url_path='delete-comment',permission_classes=[perms.CanDeleteComment])
    def delete_comment(self, request, pk):
        comment = self.get_object()
        
        comment.is_active = False
        comment.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def reply(self, request, pk):
        comment = generics.get_object_or_404(models.Comment, pk=pk, is_active=True)
        reply_data = request.data.copy()
        reply_data['post'] = comment.post.id
        reply_data['author'] = request.user.id

        if(not reply_data.get('content').strip()):
            return Response({'detail': 'Content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = serializers.CommentSerializer(data=reply_data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        reply = serializer.save(author=request.user, parent_comment=comment)

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, comment_obj=reply)

        return Response(serializers.CommentSerializer(reply, context={'request': request}).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'], url_path=r'interact/(?P<reaction>\w+)', permission_classes=[perms.IsNotRestricted])
    def interact(self, request, pk, reaction=None):
        comment = generics.get_object_or_404(models.Comment, pk=pk, is_active=True)
        return _handle_interact(request, comment, reaction, is_post=False)
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def interactions(self, request, pk):
        comment = generics.get_object_or_404(models.Comment, pk=pk, is_active=True)
        interactions = models.Interaction.objects.filter(comment=comment, is_active=True)

        page = self.paginate_queryset(interactions)
        if page is not None:
            serializer = serializers.InteractionListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.InteractionListSerializer(interactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = models.Notification.objects.filter(is_active=True)
    permission_classes = [perms.IsAuthenticated]
    serializer_class = serializers.NotificationSerializer
    pagination_class = paginators.NotificationPagination

    @action(detail=True, methods=['delete'], url_path='delete-notification',permission_classes=[perms.ObjectOwner])
    def delete_notification(self, request, pk):
        notification = generics.get_object_or_404(models.Notification, pk=pk, is_active=True)
        
        notification.is_active = False
        notification.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

class DeviceViewSet(viewsets.ViewSet, generics.ListCreateAPIView):
    queryset = models.Device.objects.filter(is_active=True)
    serializer_class = serializers.DeviceSerializer
    permission_classes = [perms.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
    
class GroupViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = models.Group.objects.filter(is_active=True)
    serializer_class = serializers.GroupSerialzier
    permissions_classes = [perms.IsAdmin]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['is_active'] = True
        serializer = self.serializer_class(data=data)
        if serializer.is_valid():
            group = serializer.save()
            return Response(self.serializer_class(group).data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=True, methods=['delete'], url_path='delete-group')
    def delete_group(self, pk):
        group = generics.get_object_or_404(models.Group, pk=pk, is_active=True)

        group.is_active = False
        group.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

def trigger_email(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'detail': 'Authentication credentials were not provided.'}, status=status.HTTP_401_UNAUTHORIZED)
    if not user.role == models.Role.ADMIN:
        return JsonResponse({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
    
    if request.method != 'POST':
        return JsonResponse({'detail': f'Method {request.method} is not allowed.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    subject = request.data.get('subject')
    content = request.data.get('content')
    recipient_type = request.data.get('recipient_type')

    if not all([subject, content, recipient_type]):
        return JsonResponse({'detail': 'subject, content and recipient_type are required.'}, status=status.HTTP_400_BAD_REQUEST)
    
    recipient_datas = request.data.get('recipients')
    if not (recipient_datas and recipient_type != 'all'):
        return JsonResponse({'detail': 'recipients can not be empty.'}, status=status.HTTP_400_BAD_REQUEST)
    
    recipients = set()
    if recipient_type == 'user':
        for recipient in recipient_datas:
            recipients.add(recipient.email)
    elif recipient_type == 'group':
        for group in recipient_datas:
            members = group['members']
            recipient.update(members.email)
    elif recipient_type == 'all':
        recipients.update(
            models.User.objects.filter(
                is_active=True, 
                is_verified=True
            ).exclude(id=user.id).values_list('email', flat=True)
        )
    else:
        return JsonResponse({'detail': 'invalid recipient_type.'}, status=status.HTTP_400_BAD_REQUEST)
    
    send_mail(
        subject,
        content,
        'copcopne@gmail.com',
        list(recipients),
        fail_silently=False,
    )
    return JsonResponse({'detail': f'Emails sent to {len(recipients)} users.'}, status=status.HTTP_200_OK)

def get_stats(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'detail': 'Authentication credentials were not provided.'}, status=status.HTTP_401_UNAUTHORIZED)
    if not user.role == models.Role.ADMIN:
        return JsonResponse({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method != 'POST':
        return JsonResponse({'detail': f'Method {request.method} is not allowed.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    object_type = request.GET.get('object_type')

    if not object_type:
        return JsonResponse({'detail': 'Missing required params: object_type.'}, status=status.HTTP_400_BAD_REQUEST)
    
    if object_type == 'user':
        obj = models.User.objects.filter(is_active=True, is_verified=True)
    elif object_type == 'post':
        obj = models.Post.objects.filter(is_active=True)
    else:
        return JsonResponse({'detail': 'Invalid object type.'}, status=status.HTTP_400_BAD_REQUEST)
    
    
    year = request.GET.get('year')
    quarter = request.GET.get('quarter')
    month = request.GET.get('month')

    try:
        year = int(year) if year else timezone.now().year
        quarter = int(quarter) if quarter else None
        if quarter and (quarter < 1 or quarter > 4):
            return JsonResponse({'detail': 'Invalid quarter.'}, status=status.HTTP_400_BAD_REQUEST)
        month = int(month) if month else None
        if month and (month < 1 or month > 12):
            return JsonResponse({'detail': 'Invalid month.'}, status=status.HTTP_400_BAD_REQUEST)
        
    except ValueError:
        return JsonResponse({'detail': 'Invalid param type.'}, status=status.HTTP_400_BAD_REQUEST)
    
    if quarter and month:
        return JsonResponse({'detail': 'Cannot filter by both quarter and month.'}, status=status.HTTP_400_BAD_REQUEST)
    
    if quarter:
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        start = make_aware(datetime(year, start_month, 1))
        if end_month == 12:
            end = make_aware(datetime(year + 1, 1, 1))
        else:
            end = make_aware(datetime(year, end_month + 1, 1))

        count = obj.filter(created_at__gte=start, 
                           created_at__lt=end) \
                        .count()
        label = f"Q{quarter}"

    elif month:
        count = obj.filter(created_at__year=year, created_at__month=month).count()
        label = f"Tháng {month}"

    else:
        count = obj.filter(created_at__year=year).count()
        label = f"Năm {year}"

    return JsonResponse({
        'label': label,
        'count': count if count else 0,
        'total': obj.count()
    })
