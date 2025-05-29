from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path

from ou2gether.models import User, Post, Comment, Group
from django.utils.html import mark_safe
from django import forms
from ckeditor_uploader.widgets import CKEditorUploadingWidget


class ou2getherAdminSite(admin.AdminSite):
    site_header = "Hệ thống mạng xã hội cựu sinh viên OU (OU2gether)"

admin_site = ou2getherAdminSite(name="myadmin")


class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'username', 'member_id', 'first_name', 'last_name', 'email', 'is_locked', 'is_active']
    search_fields = ['username', 'first_name', 'last_name']
    list_filter = ['is_active', 'is_locked']
    list_editable =['is_active', 'is_locked']
    list_per_page = 10
    readonly_fields = ['username', 'first_name', 'last_name', 'role']
    
    def get_fields(self, request, obj = ...):
        if obj:
            return [
                'username', 'first_name', 'last_name', 'email', 'role', 
                'must_change_password', 'password_set_deadline','is_locked', 'is_active'
            ]
        else:
            return ['username', 'first_name', 'last_name', 'email', 'role', 'member_id']


    def has_delete_permission(self, request, obj=None):
        return False

class PostAdmin(admin.ModelAdmin):
    list_display = ['id', 'author', 'content', 'post_type', 'is_shared', 'can_comment', 'is_active']
    search_fields = ['author', 'content']
    list_display_links = None
    list_filter = ['post_type', 'can_comment']
    list_editable =['is_active']
    list_per_page = 10
    readonly_fields = ['created_at', 'updated_at']

    def has_change_permission(self, request, obj=None):
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        return False

class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'author', 'post', 'content', 'is_edited', 'is_active']
    list_display_links = None
    search_fields = ['author', 'content']
    list_editable =['is_active']
    list_per_page = 10

    def has_change_permission(self, request, obj=None):
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        return False

class GroupAdmin(admin.ModelAdmin):
    list_display =['id', 'name']
    search_fields = ['name']
    list_per_page = 10

admin_site.register(User, UserAdmin)
admin_site.register(Post, PostAdmin)
admin_site.register(Group, GroupAdmin)
admin_site.register(Comment, CommentAdmin)