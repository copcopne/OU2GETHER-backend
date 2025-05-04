from django.db import models
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class MediaModel(BaseModel):
    file = CloudinaryField()

    class Meta:
        abstract = True


class Role(models.IntegerChoices):
    ADMIN = 0, 'Admin'
    LECTURER = 1, 'Lecturer'
    STUDENT = 2, 'Student'
    

class User(AbstractUser):
    member_id = models.CharField(max_length=12, unique=True)
    role = models.PositiveSmallIntegerField(choices=Role.choices, default=Role.ADMIN)
    bio = models.TextField(null=True, blank=True)
    avatar = CloudinaryField()
    cover = CloudinaryField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)


class PostChoices(models.IntegerChoices):
    TEXT = 0, 'Text'
    IMAGE = 1, 'Image'
    POLL = 2, 'Poll'


class Post(BaseModel):
    content = models.TextField()
    type = models.PositiveSmallIntegerField(choices=PostChoices.choices)
    is_commendable = models.BooleanField(default=True)
    is_edited = models.BooleanField(default=False)
    
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        ordering = ['-created_at']


class PostMedia(MediaModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='media')
    media_type = models.CharField(max_length=10, choices=[('image','Image'),('video','Video')])
    
    class Meta:
        ordering = ['-created_at']


class PostPoll(BaseModel):
    question = models.CharField(max_length=255)

    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='poll')


class PollOption(BaseModel):
    content = models.CharField(max_length=255)

    post_poll = models.ForeignKey(PostPoll, on_delete=models.CASCADE, related_name='options')


class PollVote(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='votes')

    poll_option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='poll_votes')


class InteractionChoices(models.IntegerChoices):
    LIKE = 0, 'Like'
    LOVE = 1, 'Love'
    HAHA = 2, 'Haha'
    WOW = 3, 'Wow'
    SAD = 4, 'Sad'
    ANGRY = 5, 'Angry'


class Interaction(BaseModel):
    type = models.PositiveSmallIntegerField(choices=InteractionChoices.choices)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey("Comment", on_delete=models.CASCADE , null=True, blank=True)
    share = models.ForeignKey("Share", on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'post'],
                name='unique_user_post_interaction'
            ),
            models.UniqueConstraint(
                fields=['user', 'comment'],
                name='unique_user_comment_interaction'
            ),
            models.UniqueConstraint(
                fields=['user', 'share'],
                name='unique_user_share_interaction'
            ),
        ]


class Comment(BaseModel):
    content = models.TextField()
    is_edited = models.BooleanField(default=False)
    
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    parent_comment = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, db_index=True, related_name='replies')


class CommentMedia(MediaModel):
    comment = models.OneToOneField(Comment, on_delete=models.CASCADE, related_name='media')
    media_type = models.CharField(max_length=10, choices=[('image','Image'),('video','Video')])


class Share(BaseModel):
    content = models.TextField()

    author = models.ForeignKey(User, on_delete=models.CASCADE)
    shared_post = models.ForeignKey(Post, on_delete=models.SET_NULL, null=True, blank=True, related_name='shares')


class Device(BaseModel):
    device_token = models.CharField(max_length=255, unique=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE)


class Notification(BaseModel):
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    target_type = models.CharField(max_length=10, choices=[('post', 'Post'), ('comment', 'Comment'), ('share', 'Share')])
    target_id = models.BigIntegerField()

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ['-created_at']


class Message(BaseModel):
    content = models.TextField()
    is_read = models.BooleanField(default=False)

    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sender')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='receiver')

    class Meta:
        ordering = ['-created_at']


class MessageMedia(MediaModel):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='message_media')


class Follow(BaseModel):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followings')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')


class Block(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocking')
    blocked_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by')

    class Meta:
        unique_together = ('user', 'blocked_user')