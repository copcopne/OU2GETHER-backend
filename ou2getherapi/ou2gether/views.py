from rest_framework import viewsets, generics, status, parsers, permissions
from rest_framework.decorators import action
from cloudinary.uploader import upload
from rest_framework.response import Response
from django.core.files.uploadedfile import InMemoryUploadedFile
from ou2gether.utils import handle_media_upload
from ou2gether.models import User, Post, Comment, CommentMedia, PostMedia, PostPoll
from ou2gether import serializers, perms, paginators

class UserViewSet(viewsets.ViewSet, generics.ListCreateAPIView):
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

    def create(self, request, *args, **kwargs):
        post_data = request.data.copy()
        post_data['author'] = request.user.id

        serializer = self.get_serializer(data=post_data)
        serializer.is_valid(raise_exception=True)
        post = serializer.save()

        files = request.FILES.getlist('media')
        if files:
            handle_media_upload(files, post_obj=post)

        return Response(serializers.PostSerializer(post).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], permission_classes=[perms.PostOwner])
    def update_post(self, request, pk):
        pass
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

    @action(detail=True, methods=['delete'], permission_classes=[perms.PostOwner, perms.Admin])
    def delete_post(self, request, pk):
        post = generics.get_object_or_404(Post, pk=pk, is_active=True)
        if request.user != post.author:
            return Response({"detail":"You don't have permission to delete this post."}, status=status.HTTP_403_FORBIDDEN)
        
        post.is_active = False
        post.save()
        return Response({"detail":"Post deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
    
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
            handle_media_upload(files, comment_obj=comment)

        return Response(serializers.CommentSerializer(comment).data, status=status.HTTP_201_CREATED)


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
            handle_media_upload(files, comment_obj=comment)

        return Response(serializers.CommentSerializer(comment).data)

    @action(detail=True, methods=['delete'], permission_classes=[perms.CommentOwner, perms.Admin])
    def delete_comment(self, request, pk):
        comment = generics.get_object_or_404(Comment, pk=pk, is_active=True)
        if request.user != comment.author:
            return Response({"detail":"You don't have permission to delete this comment."}, status=status.HTTP_403_FORBIDDEN)
        
        comment.is_active = False
        comment.save()
        return Response({"detail":"Comment deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
    
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
            handle_media_upload(files, comment_obj=reply)

        return Response(serializers.CommentSerializer(reply).data, status=status.HTTP_201_CREATED)



