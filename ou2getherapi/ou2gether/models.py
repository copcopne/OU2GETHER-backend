from django.db import models
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class ImageModel(models.Model):
    image = CloudinaryField(null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class Role(models.IntegerChoices):
    ADMIN = 1, 'Admin'
    LECTURER = 2, 'Lecturer'
    STUDENT = 3, 'Student'
    

class User(AbstractUser):
    role = models.PositiveSmallIntegerField(choices=Role.choices, default=Role.STUDENT)
    bio = models.TextField()
    personal_email = models.EmailField()


class UserStudent(models.Model):
    student_id = models.CharField(max_length=10, unique=True)
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)


class UserLecturer(models.Model):
    lecturer_id = models.CharField(max_length=10, unique=True)

    user = models.OneToOneField(User, on_delete=models.CASCADE)


class UserAvatar(ImageModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class UserCover(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class PostChoices(models.IntegerChoices):
    TEXT = 1, 'Text'
    IMAGE = 2, 'Image'
    POLL = 3, 'Poll'


class Post(BaseModel):
    content = models.TextField()
    type = models.PositiveSmallIntegerField(choices=PostChoices.choices)
    is_commendable = models.BooleanField(default=True)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class PostImage(ImageModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)


class PostPoll(BaseModel):
    question = models.CharField(max_length=255)


class PollOption(BaseModel):
    content = models.CharField(max_length=255)

    post_poll = models.ForeignKey(PostPoll, on_delete=models.CASCADE)


class PollVotes(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    poll_option = models.ForeignKey(PollOption, on_delete=models.CASCADE)


class InterractionChoices(models.IntegerChoices):
    LIKE = 1, 'Like'
    LOVE = 2, 'Love'
    HAHA = 3, 'Haha'
    WOW = 4, 'Wow'
    SAD = 5, 'Sad'
    ANGRY = 6, 'Angry'


class Interaction(BaseModel):
    type = models.PositiveSmallIntegerField(choices=InterractionChoices.choices)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey("Comment", on_delete=models.CASCADE , null=True, blank=True)
    share = models.ForeignKey("Share", on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = ('user', 'post', 'comment', 'share')


class Comment(BaseModel):
    content = models.TextField()
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    parent_comment = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, db_index=True)


class CommentImage(ImageModel):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)


class Share(BaseModel):
    content = models.TextField()

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)


class Notification(BaseModel):
    # title = models.CharField(max_length=255)
    # content = models.TextField()
    # is_read = models.BooleanField(default=False)
    # target_type = models.CharField(max_length=10, choices=[('post', 'Post'), ('comment', 'Comment'), ('share', 'Share')])
    # target_id = models.IntegerField()

    # user = models.ForeignKey(User, on_delete=models.CASCADE)
    pass


class Conversation(BaseModel):
    pass


class ConversationMember(BaseModel):
    pass


class Message(BaseModel):
    pass


class MessageStatus(BaseModel):
    pass


class Follow(BaseModel):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='follower')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')


class BlockList(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    blocked_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_user')

    class Meta:
        unique_together = ('user', 'blocked_user')