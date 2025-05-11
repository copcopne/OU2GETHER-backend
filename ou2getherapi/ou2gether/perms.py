from rest_framework import permissions
from ou2gether.models import Post, Comment, Block, Role

class IsAdmin(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view)

class IsAuthenticated(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_verified

class CommentOwner(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, comment):
        return super().has_object_permission(request, view, comment) and request.user == comment.author
    
class PostOwner(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, post):
        return super().has_object_permission(request, view, post) and request.user == post.author
    
class ObjectOwner(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return super().has_object_permission(request, view, obj) and request.user == obj.user
    
class CanDeleteComment(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        is_comment_owner = request.user == obj.author
        is_post_owner = request.user == obj.post.author
        is_admin = request.user and request.user.role == Role.ADMIN

        return is_comment_owner or is_post_owner or is_admin

class CanDeletePost(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        is_post_owner = request.user == obj.author
        is_admin = request.user and request.user.role == Role.ADMIN
        
        return is_post_owner or is_admin


class IsNotRestricted(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Post) or isinstance(obj, Comment):
            target_user = obj.author
        else:
            target_user = obj

        me = request.user
        blocked_by_me = Block.objects.filter(user=me, blocked_user=target_user).exists()
        blocked_me = Block.objects.filter(user=target_user, blocked_user=me).exists()

        return super().has_object_permission(request, view, obj) and not (blocked_by_me or blocked_me)
