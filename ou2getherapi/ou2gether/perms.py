from rest_framework import permissions
from ou2gether.models import Post, Comment, Block, Role


class IsAuthenticated(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_verified and not request.user.is_locked

class IsAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == Role.ADMIN

class CommentOwner(IsAuthenticated):
    def has_object_permission(self, request, view, comment):
        return super().has_object_permission(request, view, comment) and request.user == comment.author
    
class PostOwner(IsAuthenticated):
    def has_object_permission(self, request, view, post):
        return super().has_object_permission(request, view, post) and request.user == post.author
    
class ObjectOwner(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return super().has_object_permission(request, view, obj) and request.user == obj.user
    
class CanDeleteComment(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        
        is_comment_owner = request.user == obj.author
        is_post_owner = request.user == obj.post.author
        is_admin = request.user and request.user.role == Role.ADMIN

        return is_comment_owner or is_post_owner or is_admin

class CanDeletePost(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        
        is_post_owner = request.user == obj.author
        is_admin = request.user and request.user.role == Role.ADMIN
        
        return is_post_owner or is_admin

class IsNotRestricted(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Post) or isinstance(obj, Comment):
            target_user = obj.author
        else:
            target_user = obj

        me = request.user
        blocked_by_me = Block.objects.filter(user=me, blocked_user=target_user).exists()
        blocked_me = Block.objects.filter(user=target_user, blocked_user=me).exists()

        return super().has_object_permission(request, view, obj) and not (blocked_by_me or blocked_me)
