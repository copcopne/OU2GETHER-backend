from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path

from ou2gether import models
from django.db.models import Count
from django.db.models.functions import TruncDate, TruncMonth
from datetime import datetime
from django.utils import timezone
from django.utils.timezone import make_aware


class ou2getherAdminSite(admin.AdminSite):
    site_header = "Hệ thống mạng xã hội cựu sinh viên OU (OU2gether)"

    def get_urls(self):
        return [path('stats/', self.stats, name='stats')] + super().get_urls()

    def stats(self, request):
        object_type = request.GET.get('object_type', '')
        report_type = request.GET.get('report_type', '')
        month_str = request.GET.get('month', '')
        quarter_str = request.GET.get('quarter', '')
        year_str = request.GET.get('year', timezone.now().year)

        qs = models.User.objects.filter(is_active=True, is_verified=True) if object_type == 'users' else models.Post.objects.filter(is_active=True)

        year = timezone.now().year
        quarter = 0
        month = 0
        try:
            year = int(year_str) if year_str else year

            quarter = int(quarter_str) if quarter_str else 0
            if quarter < 0 or quarter > 4:
                quarter = 0

            month = int(month_str) if month_str else 0
            if month < 1 or month > 12:
                month = 0

        except ValueError:
            year = timezone.now().year
            quarter = 0
            month = 0

        label = ''
        count = 0
        if report_type == 'quarter':
            if quarter > 0:
                start_month = (quarter - 1) * 3 + 1
                end_month = start_month + 2
                start = make_aware(datetime(year, start_month, 1))
                if end_month == 12:
                    end = make_aware(datetime(year + 1, 1, 1))
                else:
                    end = make_aware(datetime(year, end_month + 1, 1))

                count = qs.filter(created_at__gte=start, 
                                created_at__lt=end) \
                                .count()
                label = f"Q{quarter}"

        elif report_type == 'month':
            if month > 0:
                count = qs.filter(created_at__year=year, created_at__month=month).count()
                label = f"Tháng {month}"
        
        elif report_type == 'year':
                count = qs.filter(created_at__year=year).count()
                label = f"Năm {year}"

        data = {
            'label': label,
            'count': count,
            'total': qs.count() if label else 0
        }
        
        context = {
            'object_type': object_type,
            'report_type': report_type,
            'month_value': month_str,
            'quarter_value': quarter_str,
            'year_value': year_str,
            'year_list': [y for y in range(datetime.now().year, datetime.now().year - 6, -1)],
            'data': data,
        }

        return TemplateResponse(request, 'admin/stats.html', context)


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

admin_site.register(models.User, UserAdmin)
admin_site.register(models.Post, PostAdmin)
admin_site.register(models.Group, GroupAdmin)
admin_site.register(models.Comment, CommentAdmin)