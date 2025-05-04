from rest_framework import permissions


class Admin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 0

class CommentOwner(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, comment):
        return super().has_permission(request, view) and request.user == comment.user
    
class PostOwner(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, post):
        return super().has_permission(request, view) and request.user == post.user