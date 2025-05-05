from rest_framework import viewsets, generics, status, parsers, permissions
from rest_framework.decorators import action
from cloudinary.uploader import upload
from rest_framework.response import Response
from ou2gether.models import User, Post, PostType, Comment, PostPoll, PollOption, Interaction, InteractionChoices, PostMedia, CommentMedia
from ou2gether import serializers, perms, paginators


def _handle_media_upload(files, comment_obj=None, post_obj=None):
    for file in files:
        type = 'image' if file.content_type.startswith('image/') else 'video'
        upload_result = upload(file, resource_type=type)
        path = f"{upload_result['resource_type']}/upload/v{upload_result['version']}/{upload_result['public_id']}.{upload_result['format']}"
        if comment_obj:
            CommentMedia.objects.create(
                comment=comment_obj,
                file=path,
                media_type=type
            )
            comment_obj.refresh_from_db()
        else:
            PostMedia.objects.create(
                post=post_obj,
                file=path,
                media_type=type
            )
            post_obj.refresh_from_db()


def _handle_interact(request, target_obj, reaction, is_post=True):
    reaction = reaction.upper()

    try:
        reaction_value = InteractionChoices[reaction]
    except KeyError:
        return Response({'detail': 'Invalid interaction.'}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    filter_kwargs = {'user': user}
    filter_kwargs['post' if is_post else 'comment'] = target_obj

    existing = Interaction.objects.filter(**filter_kwargs).first()

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


class UserViewSet(viewsets.ViewSet, generics.CreateAPIView):
    queryset = User.objects.filter(is_active=True)
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
    

class PostViewSet(viewsets.ViewSet,generics.ListCreateAPIView):
    queryset = Post.objects.filter(is_active=True)
    serializer_class = serializers.PostSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = paginators.PostPagination
    parser_classes = [parsers.MultiPartParser]

    def create(self, request, *args, **kwargs):
        post_data = request.data.copy()
        files = request.FILES.getlist('media')
        has_poll = bool(post_data.get('poll'))
        has_media = bool(files)

        if has_poll and has_media:
            return Response({'detail': 'Cannot create a post with both poll and media.'}, status=status.HTTP_400_BAD_REQUEST)

        post_data['author'] = request.user.id
        if has_poll:
            post_data['type'] = PostType.POLL
        elif has_media:
            post_data['type'] = PostType.MEDIA
        else:
            post_data['type'] = PostType.TEXT

        serializer = self.get_serializer(data=post_data)
        serializer.is_valid(raise_exception=True)
        post = serializer.save()

        if has_media:
            _handle_media_upload(files, post_obj=post)

        return Response(serializers.PostSerializer(post).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], permission_classes=[perms.PostOwner])
    def update_post(self, request, pk):
        # post = generics.get_object_or_404(Post, pk=pk, is_active=True)
        
        # if request.user != post.author:
        #     return Response({"detail": "You don't have permission to edit this post."}, status=status.HTTP_403_FORBIDDEN)
        
        # post.is_edited = True
        
        # for k, v in request.data.items():
        #     if k in ['content', 'media', 'poll', 'is_commendable']:
        #         if k == 'media':
        #             # Xóa tất cả media hiện tại trước khi thêm mới
        #             post.media.all().delete()
        #             for media in v:
        #                 # Giả sử media là file từ request.FILES
        #                 if isinstance(media, InMemoryUploadedFile):  # Kiểm tra xem có phải file không
        #                     # Cloudinary sẽ tự xử lý upload tệp
        #                     post_media = PostMedia.objects.create(post=post, file=media)
        #                     post.media.add(post_media)
                
        #         elif k == 'poll':
        #             post.poll.clear()
        #             for poll_data in v:
        #                 post_poll = PostPoll.objects.create(post=post, **poll_data)
        #                 post.poll.add(post_poll)
        #         else:
        #             setattr(post, k, v)

        # post.save()
        # return Response(serializers.PostSerializer(post).data)

        post = generics.get_object_or_404(Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to edit this post."}, status=status.HTTP_403_FORBIDDEN)
        
        post.is_edited = True
        if 'content' in request.data:
            post.content = request.data['content']
        if 'is_commendable' in request.data:
            post.is_commendable = request.data['is_commendable']
        post.save()

        if 'media' in request.FILES:
            post.media.all().delete()
            files = request.FILES.getlist('media')
            _handle_media_upload(files, post_obj=post)

        # 3. Poll (nếu có payload poll)
        #    request.data['poll'] = {
        #        "question": "...", 
        #        "options": [
        #           {"id": 5, "content": "Sửa option 5"},
        #           {"content": "Option mới"}
        #        ]
        #    }
        poll_data = request.data.get('poll', None)
        if poll_data is not None:
            if not hasattr(post, 'poll'):
                post.poll = PostPoll.objects.create(post=post, question=poll_data['question'])
                for opt in poll_data.get('options', []):
                    PollOption.objects.create(post_poll=post.poll, content=opt['content'])
            else:
                serializer = serializers.PostPollSerializer(instance=post.poll, data=poll_data)
                serializer.is_valid(raise_exception=True)
                serializer.save()
        
        return Response(self.get_serializer(post).data)


    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def share(self, request, pk):
        shared_post = generics.get_object_or_404(Post, pk=pk, is_active=True)
    
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        share = serializer.save(
            author=request.user,
            type=PostType.TEXT,
            is_shared=True,
            shared_post=shared_post
        )

        return Response(self.get_serializer(share).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], permission_classes=[perms.PostOwner, perms.Admin])
    def delete_post(self, request, pk):
        post = generics.get_object_or_404(Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to delete this post."}, status=status.HTTP_403_FORBIDDEN)
        
        post.is_active = False
        post.save()
        return Response({"detail":"Post deleted successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def comment(self, request, pk):
        post = generics.get_object_or_404(Post, pk=pk, is_active=True)
        comment_data = request.data.copy()
        comment_data['post'] = post.id
        comment_data['author'] = request.user.id

        serializer = serializers.CommentSerializer(data=comment_data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(author=request.user)

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, comment_obj=comment)

        return Response(serializers.CommentSerializer(comment).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def interactions(self, request, pk):
        post = generics.get_object_or_404(Post, pk=pk, is_active=True)
        interactions = Interaction.objects.filter(post=post, is_active=True)
        serializer = serializers.InteractionListSerializer(interactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


    @action(detail=True, methods=['post'], url_path=r'interact/(?P<reaction>\w+)')
    def interact(self, request, pk, reaction=None):
        post = generics.get_object_or_404(Post, pk=pk, is_active=True)
        return _handle_interact(request, post, reaction, is_post=True)


class CommentViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = Comment.objects.filter(is_active=True)
    serializer_class = serializers.CommentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = paginators.CommentPagination

    @action(detail=True, methods=['patch'], permission_classes=[perms.CommentOwner])
    def update_comment(self, request, pk):
        comment = generics.get_object_or_404(Comment, pk=pk, is_active=True)
        if request.user != comment.author:
            return Response({"detail":"You don't have permission to edit this comment."}, status=status.HTTP_403_FORBIDDEN)
        
        comment.__setattr__('is_edited', True)
        content = request.data.get('content')
        if content:
            comment.content = content
        comment.save()

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, comment_obj=comment)

        return Response(serializers.CommentSerializer(comment).data)

    @action(detail=True, methods=['delete'], permission_classes=[perms.CommentOwner, perms.Admin, perms.PostOwner])
    def delete_comment(self, request, pk):
        comment = generics.get_object_or_404(Comment, pk=pk, is_active=True)
        if request.user != comment.author:
            return Response({"detail":"You don't have permission to delete this comment."}, status=status.HTTP_403_FORBIDDEN)
        
        comment.is_active = False
        comment.save()
        return Response({"detail":"Comment deleted successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def reply(self, request, pk):
        comment = generics.get_object_or_404(Comment, pk=pk, is_active=True)
        reply_data = request.data.copy()
        reply_data['post'] = comment.post.id
        reply_data['author'] = request.user.id

        serializer = serializers.CommentSerializer(data=reply_data)
        serializer.is_valid(raise_exception=True)
        reply = serializer.save(author=request.user, parent_comment=comment)

        files = request.FILES.getlist('media')
        if files:
            _handle_media_upload(files, comment_obj=reply)

        return Response(serializers.CommentSerializer(reply).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'], url_path=r'interact/(?P<reaction>\w+)')
    def interact(self, request, pk, reaction=None):
        comment = generics.get_object_or_404(Comment, pk=pk, is_active=True)
        return _handle_interact(request, comment, reaction, is_post=False)

