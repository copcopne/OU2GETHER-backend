from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('users', views.UserViewSet, basename='user')
router.register('posts', views.PostViewSet, basename='post')
router.register('comments', views.CommentViewSet, basename='comment')
router.register('notifications', views.NotificationViewSet, basename='notification')
router.register('devices', views.DeviceViewSet, basename='device')


urlpatterns = [
    path('', include(router.urls))
]