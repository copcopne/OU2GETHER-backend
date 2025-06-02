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
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes


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
        else:
            existing.type = reaction_value
            existing.is_active = True
            existing.save()
    else:
        serializer = serializers.InteractionCreateSerializer(
            data={'type': reaction_value},
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        kwargs = {'post': target_obj} if is_post else {'comment': target_obj}
        serializer.save(**kwargs)

    if (is_post):
        return Response(serializers.PostSerializer(target_obj, context={'request': request}).data, status=status.HTTP_200_OK)
    else:
        return Response(serializers.CommentSerializer(target_obj, context={'request': request}).data, status=status.HTTP_200_OK)


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

        only_verified_users = params.get('verified')
        if only_verified_users:
            queryset = queryset.filter(is_verified=True)

        keyword = params.get('kw')
        if keyword:
            queryset = queryset.filter(Q(first_name__istartswith=keyword) | Q(last_name__istartswith=keyword) | Q(username__iexact=keyword))
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

        if 'role' not in user_data:
            user_data['role'] = models.Role.STUDENT

        current_user = request.user
        if current_user.is_authenticated:
            if current_user.role == models.Role.ADMIN:
                user_data['is_verified'] = True
                user_data['password'] = 'ou@123'
                user_data['must_change_password'] = True
                user_data['password_set_deadline'] = timezone.now() + timezone.timedelta(days=1)
            else:
                return Response({'detail': 'You do not have permission to create this user.'}, status=status.HTTP_403_FORBIDDEN)
        
        else: 
            user_data['is_verified'] = False
        serializer = serializers.UserSerializer(data=user_data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(serializers.UserSerializer(user, context={'request': request}).data, 
                        status=status.HTTP_201_CREATED)

    @action(methods=['get', 'patch'], url_path='current-user', detail=False, permission_classes=[permissions.IsAuthenticated])
    def get_current_user(self, request):
        u = request.user
        
        if u.is_locked == True:
            return Response({'detail': 'Your account has been locked.'}, status=status.HTTP_403_FORBIDDEN)
        
        if u.must_change_password:
            now = timezone.now()
            if now > u.password_set_deadline:
                u.is_locked = True
                u.save()
                return Response({'detail': 'Your account has been locked.'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'PATCH':
            for k, v in request.data.items():
                if k == 'password':
                    if u.must_change_password == True:
                        u.must_change_password = False
                        u.reset_password_deadline = None
                    u.set_password(v)
                elif k in ['avatar', 'cover', 'first_name', 'last_name', 'bio', 'email']:
                    setattr(u, k, v)
            u.save()

        return Response(serializers.UserSerializer(u, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='block-user',permission_classes=[perms.IsNotRestricted])
    def block_user(self, request, pk):
        target_user = self.get_object()

        models.Block.objects.create(user=request.user, blocked_user=target_user)
        return Response({'detail': 'User blocked successfully.'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='unblock-user',permission_classes=[permissions.IsAuthenticated])
    def unblock_user(self, request, pk):
        target_user = self.get_object()

        if request.user == target_user:
            return Response({'detail': 'Cannot unblock yourself.'}, status=status.HTTP_400_BAD_REQUEST)

        models.Block.objects.filter(user=request.user, blocked_user=target_user).delete()
        return Response({'detail': 'User unblocked successfully.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def follow(self, request, pk):
        user_to_follow = self.get_object()

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
        user = self.get_object()

        followers_qs = _get_followers_or_following(user, is_follower=True)

        page = self.paginate_queryset(followers_qs)
        if page is not None:
            serializer = serializers.MinimalUserSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.MinimalUserSerializer(followers_qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def following(self, request, pk):
        user = self.get_object()

        following_qs = _get_followers_or_following(user, is_follower=False)

        page = self.paginate_queryset(following_qs)
        if page is not None:
            serializer = serializers.MinimalUserSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = serializers.MinimalUserSerializer(following_qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='unverified-users',permission_classes=[permissions.IsAdminUser])
    def unverified_users(self, request):
        params = request.query_params
        kw = params.get("kw")

        unverified_users = models.User.objects.filter(is_verified=False, is_active=True)

        if kw:
            unverified_users = unverified_users.ffilter(Q(first_name__istartswith=kw) | Q(last_name__istartswith=kw) | Q(username__iexact=kw))
        page = self.paginate_queryset(unverified_users)

        if page is not None:
            serializer = serializers.UserSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = serializers.UserSerializer(unverified_users, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def verify(self, request, pk):
        user = self.get_object()
        
        if user.is_verified:
            return Response({'detail': 'User is already verified.'}, status=status.HTTP_400_BAD_REQUEST)

        user.is_verified = True
        user.save()
        send_mail(
            'Thông báo tình trạng tài khoản',
            f"Chào {user.first_name},\n"
            "Tài khoản của bạn đã được xác nhận và đã có thể truy cập vào hệ thống.\n"
            "Chúc bạn có trải nghiệm tốt.",
            'copcopne@gmail.com',
            [user.email],
            fail_silently=False,
        )
        return Response({'detail': 'User verified successfully.'}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='locked-users',permission_classes=[permissions.IsAdminUser])
    def locked_users(self, request):
        params = request.query_params
        kw = params.get("kw")

        locked_users = models.User.objects.filter(is_locked=True, is_active=True)

        if kw:
            locked_users = locked_users.filter(Q(first_name__istartswith=kw) | Q(last_name__istartswith=kw) | Q(username__iexact=kw))
        page = self.paginate_queryset(locked_users)

        if page is not None:
            serializer = serializers.UserSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = serializers.UserSerializer(locked_users, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='reset-password-deadline', permission_classes=[permissions.IsAdminUser])
    def reset_password_deadline(self, request, pk):
        user = self.get_object()

        if user.must_change_password != True or user.is_locked != True:
            return Response({'detail': "User does not need to reset password deadline."}, status=status.HTTP_400_BAD_REQUEST)

        user.must_change_password = True
        user.is_locked = False
        user.password_set_deadline = timezone.now() + timezone.timedelta(days=1)
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
        if params.get('all'):
            queryset = queryset.filter(Q(post_type=models.PostType.TEXT) | Q(post_type=models.PostType.MEDIA), is_active=True)
        if params.get('userId'):
            user_id = params.get('userId')
            queryset = models.Post.objects.filter(author__id=user_id, is_active=True)
        if params.get('poll'):
            now = timezone.now()
            queryset = models.Post.objects.filter(post_type=models.PostType.POLL, poll__end_time__gt=now, is_active=True)
        if params.get('following'):
            followed_user_ids = models.Follow.objects.filter(follower=self.request.user, is_active=True).values_list('following_id', flat=True)
            queryset = queryset.filter(author__in=followed_user_ids)

        return queryset

    
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
            poll_data = post_data.pop('poll', None)

            if not isinstance(poll_data, dict):
                return Response({'detail': 'Poll must be a JSON object.'}, status=status.HTTP_400_BAD_REQUEST)

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

            poll_data['options'] = [{'content': opt} for opt in poll_data.get('options', [])]

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

        return Response(serializers.PostSerializer(post, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)
    
    def destroy(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        
        if not perms.CanDeletePost().has_object_permission(request, self, post):
            return Response({'detail': 'You do not have permission to delete this post.'}, status=status.HTTP_403_FORBIDDEN)

        post.is_active = False
        post.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['patch'], url_path='update-post', permission_classes=[perms.PostOwner])
    def update_post(self, request, pk):
        post = self.get_object()

        is_edited = False
        for k, v in request.data.items():
            if k =='poll':
                if isinstance(v, str):
                    try:
                        poll_data = json.loads(v)
                    except json.JSONDecodeError:
                        return Response({'detail': 'Invalid poll JSON.'}, status=status.HTTP_400_BAD_REQUEST)
                elif isinstance(v, dict):
                    poll_data = v
                else:
                    return Response({'detail': 'Invalid poll data format.'}, status=status.HTTP_400_BAD_REQUEST)
                
                if poll_data.get('end_time'):
                    try:
                        dt = parse_datetime(poll_data['end_time'])
                        if not dt:
                            raise ValueError()
                        if timezone.is_naive(dt):
                            dt = timezone.make_aware(dt, timezone.get_current_timezone())
                        if dt < timezone.now():
                            return Response({'detail': 'Poll end time must be in the future.'}, status=status.HTTP_400_BAD_REQUEST)
                        poll_data['end_time'] = dt
                    except Exception:
                        return Response({'detail': 'Invalid end_time format.'}, status=status.HTTP_400_BAD_REQUEST)
                        
                if 'options' in poll_data:
                    new_options = []
                    for opt in poll_data['options']:
                        if isinstance(opt, str):
                            opt = {'content': opt}

                        if opt.get('to_delete') and opt.get('id'):
                            models.PollOption.objects.filter(id=opt['id'], post_poll=post.poll, is_active=True).update(is_active=False)
                        else:
                            new_options.append(opt)

                    poll_data['options'] = new_options
                    
                serializer = serializers.PostPollSerializer(instance=post.poll, data=poll_data, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                is_edited = True

            elif k == 'content':
                if not v.strip():
                    return Response({'detail': 'Content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
                post.content = v
                is_edited = True

            elif k == 'can_comment':
                post.can_comment = str(v).lower() in ['true', '1']
                is_edited = True

        if is_edited:
            post.is_edited = True
            post.save()
            return Response(self.get_serializer(post, context={'request': request}).data, status=status.HTTP_200_OK)
        
        return Response({"detail":"No changes were made."}, status=status.HTTP_400_BAD_REQUEST)

    
    @action(detail=True, methods=['post'], url_path='update-post/upload-media', permission_classes=[perms.PostOwner])
    def upload_media(self, request, pk):
        post = self.get_object()

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
        post = self.get_object()

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
        shared_post = self.get_object()

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

    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def comments(self, request, pk):
        post = self.get_object()

        comments = models.Comment.objects.filter(post=post, is_active=True)
        page = self.paginate_queryset(comments)
        if page is not None:
            serializer = serializers.CommentSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = serializers.CommentSerializer(comments, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def comment(self, request, pk):
        post = self.get_object()

        if post.can_comment == False:
            return Response({'detail': 'Comments are restricted on this post.'}, status=status.HTTP_403_FORBIDDEN)   
        
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

        return Response(serializers.CommentSerializer(comment, context={'request': request}).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def interactions(self, request, pk):
        post = self.get_object()

        interactions = models.Interaction.objects.filter(post=post, is_active=True)
        page = self.paginate_queryset(interactions)
        if page is not None:
            serializer = serializers.InteractionListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.InteractionListSerializer(interactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


    @action(detail=True, methods=['post'], url_path=r'interact/(?P<reaction>\w+)', permission_classes=[perms.IsNotRestricted])
    def interact(self, request, pk, reaction=None):
        post = self.get_object()

        return _handle_interact(request, post, reaction, is_post=True)
    
    @action(detail=True, methods=['post'], url_path='vote', permission_classes=[perms.IsNotRestricted])
    def vote(self, request, pk):
        post = self.get_object()

        if post.post_type != models.PostType.POLL:
            return Response({"detail":"This post is not a poll."}, status=status.HTTP_400_BAD_REQUEST)

        poll = post.poll
        if poll.end_time and timezone.now() > poll.end_time:
            return Response({"detail": "Poll has ended. Voting is closed."}, status=status.HTTP_403_FORBIDDEN)
        
        option_ids = request.data.get('option_ids', [])
        if not isinstance(option_ids, list):
            return Response({"detail": "option_ids must be a list object."}, status=status.HTTP_400_BAD_REQUEST)
        
        for oid in option_ids:
            option = generics.get_object_or_404(models.PollOption, pk=oid, post_poll=poll)
            vote_qs = models.PollVote.objects.filter(user=request.user, poll_option=option)
            if vote_qs.exists():
                vote_qs.delete()
            else:
                models.PollVote.objects.create(user=request.user, poll_option=option)

        post.refresh_from_db()
        return Response(self.get_serializer(post, context={'request': request}).data, 
                        status=status.HTTP_200_OK)


class CommentViewSet(viewsets.GenericViewSet):
    queryset = models.Comment.objects.filter(is_active=True)
    serializer_class = serializers.CommentSerializer
    permission_classes = [perms.IsAuthenticated]
    pagination_class = paginators.CommentPagination


    def destroy(self, request, pk):
        comment = generics.get_object_or_404(models.Comment, pk=pk, is_active=True)

        if not perms.CanDeleteComment().has_object_permission(request, self, comment):
            return Response({'detail': 'You do not have permission to delete this comment.'}, status=status.HTTP_403_FORBIDDEN)
         
        comment.is_active = False
        comment.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['patch'], url_path='update-comment', permission_classes=[perms.CommentOwner])
    def update_comment(self, request, pk):
        comment = self.get_object()

        comment.is_edited = True
        content = request.data.get('content')
        if content:
            comment.content = content
        comment.save()

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, comment_obj=comment)

        return Response(serializers.CommentSerializer(comment, context={'request': request}).data)
    
    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def reply(self, request, pk):
        comment = self.get_object()

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
        comment = self.get_object()

        return _handle_interact(request, comment, reaction, is_post=False)
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def interactions(self, request, pk):
        comment = self.get_object()

        interactions = models.Interaction.objects.filter(comment=comment, is_active=True)
        page = self.paginate_queryset(interactions)
        if page is not None:
            serializer = serializers.InteractionListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.InteractionListSerializer(interactions, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = models.Notification.objects.filter(is_active=True)
    permission_classes = [perms.IsAuthenticated]
    serializer_class = serializers.NotificationSerializer
    pagination_class = paginators.NotificationPagination


    def destroy(self, request, pk):
        notification = generics.get_object_or_404(models.Notification, pk=pk, is_active=True)

        if not perms.ObjectOwner().has_object_permission(request, self, notification):
            return Response({'detail': 'You do not have permission to delete this notification.'}, status=status.HTTP_403_FORBIDDEN)
        
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
    permission_classes = [perms.IsAdmin]
    pagination_class = paginators.UserPagination

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        name = data.get('name')
        member_ids = data.get('members', [])
        if not member_ids:
            return Response({"detail": "Member is required for groups."}, status=status.HTTP_400_BAD_REQUEST)
        group = models.Group.objects.create(name=name, is_active=True)

        for member_id in member_ids:
            try:
                user = models.User.objects.get(id=member_id, is_active=True)
                group.members.add(user)
            except models.User.DoesNotExist:
                continue

        serializer = self.serializer_class(group)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk):
        group = generics.get_object_or_404(models.Group, pk=pk, is_active=True)

        self.check_object_permissions(request, group)

        group.is_active = False
        group.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def retrieve(self, request, pk):
        group = generics.get_object_or_404(models.Group, pk=pk, is_active=True)
        self.check_object_permissions(request, group)
        serializer = serializers.GroupSerialzier(group, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['patch'], url_path='update')
    def partical_update(self, request, pk):
        group = self.get_object()

        name = request.data.get('name')
        member_ids = request.data.getlist('members', [])

        if name:
            group.name = name

        if member_ids:
            new_members = models.User.objects.filter(id__in=member_ids, is_active=True)
            group.members.set(new_members)

        group.save()
        
        serializer = serializers.GroupSerialzier(group, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    
@api_view(['POST'])
@permission_classes([perms.IsAdmin])
@csrf_exempt
def trigger_email(request):
    subject = request.data.get('subject')
    content = request.data.get('content')
    recipient_type = request.data.get('recipient_type')

    if not all([subject, content, recipient_type]):
        return JsonResponse({'detail': 'subject, content and recipient_type are required.'}, status=status.HTTP_400_BAD_REQUEST)
    
    recipient_ids = request.data.getlist('recipients', [])
    if not (recipient_ids or recipient_type == 'all'):
        return JsonResponse({'detail': 'recipients can not be empty.'}, status=status.HTTP_400_BAD_REQUEST)
    recipients = set()
    if recipient_type == 'user':
        for recipient_id in recipient_ids:
            user = models.User.objects.filter(id=recipient_id, is_active=True, is_verified=True).first()
            if user:
                recipients.add(user.email)
    elif recipient_type == 'group':
        for group_id in recipient_ids:
            group = models.Group.objects.filter(id=group_id, is_active=True).first()
            if group:
                emails = group.members.filter(is_active=True, is_verified=True).values_list('email', flat=True)
                recipients.update(emails)
    elif recipient_type == 'all':
        user = request.user
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

@api_view(['POST'])
@permission_classes([perms.IsAdmin])
@csrf_exempt
def get_stats(request):
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
