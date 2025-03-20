from django.db import models
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class User(AbstractUser):
    pass

class UserAvatars(models.Model):
    avatar = CloudinaryField(null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class UserCovers(models.Model):
    cover = CloudinaryField(null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class Post(BaseModel):
    content = models.TextField()
    type = models.CharField(max_length=10, choices=[('text', 'Text'), ('image', 'Image'), ('poll', 'Poll')])
    is_commendable = models.BooleanField(default=True)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)



class Interaction(BaseModel):
    type = models.CharField(max_length=10, choices=[('like', 'Like'), ('love', 'Love'), 
                                                    ('haha', 'Haha'), ('wow', 'Wow'), 
                                                    ('sad', 'Sad'), ('angry', 'Angry')])
    
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey("Comment", on_delete=models.CASCADE , null=True, blank=True)
    share = models.ForeignKey("Share", on_delete=models.CASCADE, null=True, blank=True)


class Comment(BaseModel):
    content = models.TextField()
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    parent_comment = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)


class Share(BaseModel):
    content = models.TextField()

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
