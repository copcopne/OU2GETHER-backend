from rest_framework import viewsets, generics, status, parsers, permissions
from rest_framework.decorators import action
from cloudinary.uploader import upload
from rest_framework.response import Response
from ou2gether import models
from ou2gether import serializers, perms, paginators
import json


def _handle_media_upload(files, comment_obj=None, post_obj=None):
    for file in files:
        type = 'image' if file.content_type.startswith('image/') else 'video'
        upload_result = upload(file, resource_type=type)
        path = f"{upload_result['resource_type']}/upload/v{upload_result['version']}/{upload_result['public_id']}.{upload_result['format']}"
        if comment_obj:
            models.CommentMedia.objects.create(
                comment=comment_obj,
                file=path,
                media_type=type
            )
            comment_obj.refresh_from_db()
        else:
            models.PostMedia.objects.create(
                post=post_obj,
                file=path,
                media_type=type
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
    return models.Follow.objects.filter(
        **({'following': user} if is_follower else {'follower': user})
    ).select_related('follower' if is_follower else 'following')


class UserViewSet(viewsets.ViewSet, generics.CreateAPIView):
    queryset = models.User.objects.filter(is_active=True)
    serializer_class = serializers.UserSerializer
    parser_classes = [parsers.MultiPartParser]
    pagination_class = paginators.UserPagination

    @action(methods=['get', 'patch'], url_path='current-user', detail=False, permission_classes = [permissions.IsAuthenticated])
    def get_current_user(self, request):
        u = request.user

        if request.method == 'PATCH':
            for k, v in request.data.items():
                if k == 'password':
                    u.set_password(v)
                elif k in ['avatar', 'cover', 'first_name', 'last_name', 'bio', 'email']:
                    setattr(u, k, v)
            u.save()

        return Response(serializers.UserSerializer(u).data)
    
    @action(methods=['get'], detail=False, url_path='current-user/followers', permission_classes=[permissions.IsAuthenticated])
    def current_user_followers(self, request):
        u = request.user
        followers = _get_followers_or_following(u, is_follower=True)
        serializer = serializers.FollowSerializer(followers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(methods=['get'], detail=False, url_path='current-user/following', permission_classes=[permissions.IsAuthenticated])
    def current_user_following(self, request):
        u = request.user
        following = _get_followers_or_following(u, is_follower=False)
        serializer = serializers.FollowSerializer(following, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def block_user(self, request, pk):
        target_user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        if request.user == target_user:
            return Response({'detail': 'Cannot block yourself.'}, status=status.HTTP_400_BAD_REQUEST)

        models.Block.objects.create(user=request.user, blocked_user=target_user)
        return Response({'detail': 'User blocked successfully.'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def unblock_user(self, request, pk):
        target_user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        if request.user == target_user:
            return Response({'detail': 'Cannot unblock yourself.'}, status=status.HTTP_400_BAD_REQUEST)

        models.Block.objects.filter(user=request.user, blocked_user=target_user).delete()
        return Response({'detail': 'User unblocked successfully.'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def followers(self, request, pk):
        user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        followers = _get_followers_or_following(user, is_follower=True)
        serializer = serializers.FollowSerializer(followers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def following(self, request, pk):
        user = generics.get_object_or_404(models.User, pk=pk, is_active=True)
        following = _get_followers_or_following(user, is_follower=False)
        serializer = serializers.FollowSerializer(following, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class PostViewSet(viewsets.ViewSet,generics.ListCreateAPIView):
    queryset = models.Post.objects.filter(is_active=True)
    serializer_class = serializers.PostSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = paginators.PostPagination
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]

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
            poll = models.PostPoll.objects.create(
                post=post,
                question=poll_data.get('question', '')
            )
            for opt in poll_data.get('options', []):
                opt_serializer = serializers.PollOptionSerializer(data=opt)
                opt_serializer.is_valid(raise_exception=True)
                opt_serializer.save(post_poll=poll)

        return Response(serializers.PostSerializer(post, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], permission_classes=[perms.PostOwner])
    def update_post(self, request, pk):

        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to edit this post."}, status=status.HTTP_403_FORBIDDEN)
        
        post.is_edited = True
        for k, v in request.data.items():
            if k =='poll':
                serializer = serializers.PostPollSerializer(instance=post.poll, data=v)
                serializer.is_valid(raise_exception=True)
                serializer.save()
            elif k in ['content', 'is_commendable']:
                setattr(post, k, v)
        post.save()
        return Response(self.get_serializer(post, context={'request': request}).data)
    
    @action(detail=True, methods=['post'], url_path='update_post/upload_media', permission_classes=[perms.PostOwner])
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

        return Response(serializers.PostSerializer(post, context={'request': request}).data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['delete'], url_path=r'update_post/media/(?P<media_id>\d+)', permission_classes=[perms.PostOwner])
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

        return Response({"detail": "Delete successfully."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def share(self, request, pk):
        shared_post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
    
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        share = serializer.save(
            author=request.user,
            post_type=PostType.TEXT,
            is_shared=True,
            shared_post=shared_post
        )

        return Response(self.get_serializer(share).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], permission_classes=[perms.PostOwner, permissions.IsAdminUser])
    def delete_post(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to delete this post."}, status=status.HTTP_403_FORBIDDEN)
        
        post.is_active = False
        post.save()
        return Response({"detail":"Post deleted successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'], permission_classes=[perms.IsNotRestricted])
    def comments(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        comments = models.Comment.objects.filter(post=post, is_active=True)
        serializer = serializers.CommentSerializer(comments, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def comment(self, request, pk):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        comment_data = request.data.copy()
        comment_data['post'] = post.id
        comment_data['author'] = request.user.id

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
        serializer = serializers.InteractionListSerializer(interactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


    @action(detail=True, methods=['post'], url_path=r'interact/(?P<reaction>\w+)', permission_classes=[perms.IsNotRestricted])
    def interact(self, request, pk, reaction=None):
        post = generics.get_object_or_404(models.Post, pk=pk, is_active=True)
        return _handle_interact(request, post, reaction, is_post=True)


class CommentViewSet(viewsets.ViewSet):
    queryset = models.Comment.objects.filter(is_active=True)
    serializer_class = serializers.CommentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = paginators.CommentPagination

    @action(detail=True, methods=['patch'], permission_classes=[perms.CommentOwner])
    def update_comment(self, request, pk):
        comment = generics.get_object_or_404(models.Comment, pk=pk, is_active=True)
        
        comment.__setattr__('is_edited', True)
        content = request.data.get('content')
        if content:
            comment.content = content
        comment.save()

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, comment_obj=comment)

        return Response(serializers.CommentSerializer(comment).data)

    @action(detail=True, methods=['delete'], permission_classes=[perms.CommentOwner, perms.PostOwner, permissions.IsAdminUser])
    def delete_comment(self, request, pk):
        comment = generics.get_object_or_404(models.Comment, pk=pk, is_active=True)
        
        comment.is_active = False
        comment.save()
        return Response({"detail":"Comment deleted successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[perms.IsNotRestricted])
    def reply(self, request, pk):
        comment = generics.get_object_or_404(models.Comment, pk=pk, is_active=True)
        reply_data = request.data.copy()
        reply_data['post'] = comment.post.id
        reply_data['author'] = request.user.id

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
        serializer = serializers.InteractionListSerializer(interactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = models.Notification.objects.filter(is_active=True)
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.NotificationSerializer
    pagination_class = paginators.NotificationPagination

    @action(detail=True, methods=['delete'], permission_classes=[perms.ObjectOwner])
    def delete_notification(self, request, pk):
        notification = generics.get_object_or_404(models.Notification, pk=pk, is_active=True)
        
        notification.is_active = False
        notification.save()
        return Response({"detail":"Notification deleted successfully."}, status=status.HTTP_200_OK)
    

class DeviceViewSet(viewsets.ViewSet, generics.ListCreateAPIView):
    queryset = models.Device.objects.filter(is_active=True)
    serializer_class = serializers.DeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class ConversationViewSet(viewsets.ViewSet, generics.ListCreateAPIView):
    queryset = models.Conversation.objects.filter(is_active=True)
    serializer_class = serializers.ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
