from django.contrib import admin
from django.db.models import Count
from django.template.response import TemplateResponse
from django.urls import path

from ou2gether.models import User, Post, Comment
from django.utils.html import mark_safe
from django import forms
from ckeditor_uploader.widgets import CKEditorUploadingWidget


class ou2getherAdminSite(admin.AdminSite):
    site_header = "Hệ thống mạng xã hội cựu sinh viên OU (OU2gether)"

admin_site = ou2getherAdminSite(name="myadmin")


class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'username', 'first_name', 'last_name', 'email', 'member_id']
    search_fields = ['username', 'first_name', 'last_name']
    list_filter = ['is_active', 'is_staff']
    list_editable = ['username']

    def get_fields(self, request, obj = ...):
        if obj:
            return ['username', 'first_name', 'last_name', 'email', 'is_active', 'member_id']
        else:
            return ['username', 'first_name', 'last_name', 'email', 'role', 'member_id']
        
    def get_changeform_initial_data(self, request):
        return {'role': 'lecturer'}
    
    def get_readonly_fields(self, request, obj=None):
        return ['role']
    
class PostAdmin(admin.ModelAdmin):
    list_display = ['id', 'content', 'post_type', 'is_commendable', 'is_edited']
    search_fields = ['content']
    list_filter = ['post_type', 'is_commendable']
    list_editable = ['content']
    readonly_fields = ['created_at', 'updated_at']

class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'content', 'is_edited']
    search_fields = ['content']
    list_editable = ['content']
    readonly_fields = ['created_at', 'updated_at']

admin_site.register(User, UserAdmin)
admin_site.register(Post, PostAdmin)
admin_site.register(Comment, CommentAdmin)