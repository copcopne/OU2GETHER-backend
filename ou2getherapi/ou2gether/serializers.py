from rest_framework import serializers
from ou2gether.models import (
    User, Post, Comment, Interaction, Notification, Message,
    PostMedia, PostPoll, PollOption, InteractionChoices, 
    PostType, MessageMedia, Device, Conversation, Group, Role
)
from django.utils import timezone

class UserContextMixin:
    def get_is_following(self, user):
        request = self.context.get('request')
        return request and not request.user.is_anonymous and request.user.followings.filter(following=user, is_active=True).exists()

    def get_is_myself(self, user):
        request = self.context.get('request')
        return request and not request.user.is_anonymous and request.user.id == user.id

    def get_if_mutual(self, user):
        request = self.context.get('request')
        if not request or request.user.is_anonymous:
            return False
        return (
            request.user.followings.filter(following=user, is_active=True).exists() and
            user.followings.filter(following=request.user, is_active=True).exists()
        )

    def get_number_of_followers(self, user):
        return user.followers.filter(is_active=True).count()

    def get_number_of_followings(self, user):
        return user.followings.filter(is_active=True).count()

class UserSerializer(UserContextMixin, serializers.ModelSerializer):
    is_following = serializers.SerializerMethodField()
    is_myself = serializers.SerializerMethodField()
    if_mutual = serializers.SerializerMethodField()
    number_of_followers = serializers.SerializerMethodField()
    number_of_followings = serializers.SerializerMethodField()
    
    def to_representation(self, instance):
        data = super().to_representation(instance)

        data['avatar'] = instance.avatar.url if instance.avatar else ''
        data['cover'] = instance.cover.url if instance.cover else ''

        return data

    def create(self, validated_data):
        data = validated_data.copy()

        user = User(**data)
        user.set_password(data["password"])
        user.save()

        return user
    
    def update(self, instance, validated_data):
        data = validated_data.copy()

        if 'password' in data:
            instance.set_password(data.pop('password'))

        for attr, value in data.items():
            setattr(instance, attr, value)

        instance.save()

        return instance
    
    # def validate_username(self, value):
    #     if User.objects.filter(username=value).exists():
    #         raise serializers.ValidationError("Username already exists.")
    #     return value
    
    # def validate_memeber_id(self, value):
    #     if User.objects.filter(member_id=value).exists():
    #         raise serializers.ValidationError("Member ID already exists.")
    #     return value
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'password',
            'member_id', 'avatar', 'cover', 'bio', 'role',
            'is_following', 'number_of_followers', 'number_of_followings',
            'must_change_password', 'password_set_deadline', 'is_locked', 
            'is_verified', 'date_joined',
            'is_myself', 'if_mutual'
        ]
        extra_kwargs = {
            'id': {
                'read_only': True
            },
            'is_verified': {
                'read_only': True
            },
            'date_joined': {
                'read_only': True
            },
            'password': {
                'required': True, 
                'write_only': True
            }, 
            'member_id': {
                'required': True
            },
        }


class MinimalUserSerializer(UserContextMixin, serializers.ModelSerializer):
    is_following = serializers.SerializerMethodField()
    is_myself = serializers.SerializerMethodField()
    if_mutual = serializers.SerializerMethodField()
    number_of_followers = serializers.SerializerMethodField()
    number_of_followings = serializers.SerializerMethodField()
    
    def to_representation(self, instance):
        data = super().to_representation(instance)

        data['avatar'] = instance.avatar.url if instance.avatar else ''

        return data
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'avatar', 
            'is_following', 'number_of_followers', 'number_of_followings',
            'is_myself', 'if_mutual', 'member_id'
            ]
        read_only_fields = [
            'id'
        ]


class CustomUserSerialzier(serializers.ModelSerializer):

    def to_representation(self, instance):
        data = super().to_representation(instance)

        data['avatar'] = instance.avatar.url if instance.avatar else ''

        return data

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'avatar', 'email', 'member_id'
            ]
        read_only_fields = [
            'id', 'username', 'first_name', 'last_name', 'avatar', 'email', 'member_id'
        ]

class PostMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.CharField(source='file.url')
    

    class Meta:
        model = PostMedia
        fields = ['id', 'file_url', 'created_at']


class PollOptionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    is_voted = serializers.SerializerMethodField()
    vote_count = serializers.SerializerMethodField()

    def get_vote_count(self, option):
        user = self.context['request'].user
        if user.role == Role.STUDENT:
            return 0
        return option.poll_votes.count()

    def get_is_voted(self, option):
        user = self.context['request'].user
        if user.is_authenticated:
            return option.poll_votes.filter(user=user).exists()
        return False
    

    class Meta:
        model = PollOption
        fields = ['id', 'content', 'vote_count', 'is_voted']


class PostPollSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(many=True)
    is_ended = serializers.SerializerMethodField()

    def create(self, validated_data):
        options_data = validated_data.pop('options', [])
        poll = PostPoll.objects.create(**validated_data)
        for option_data in options_data:
            PollOption.objects.create(post_poll=poll, **option_data)
        return poll

    def update(self, instance, validated_data):
        options_data = validated_data.pop('options', [])

        instance.question = validated_data.get('question', instance.question)
        instance.save()

        new_option_ids = []
        for option_data in options_data:
            option_id = option_data.get('id', None)
            if option_id:
                try:
                    option = instance.options.get(id=option_id)
                    option.content = option_data.get('content', option.content)
                    option.save()
                    new_option_ids.append(option_id)
                except PollOption.DoesNotExist:
                    continue
            else:
                new_option = PollOption.objects.create(post_poll=instance, **option_data)
                new_option_ids.append(new_option.id)

        instance.options.exclude(id__in=new_option_ids).delete()

        return instance
    
    def get_is_ended(self, poll):
        now = timezone.now()
        return now >= poll.end_time
    
    class Meta:
        model = PostPoll
        fields = ['id', 'post', 'question', 'options', 'end_time', 'is_ended']



class PostSerializer(serializers.ModelSerializer):
    author = MinimalUserSerializer(read_only=True)
    poll = PostPollSerializer(many=False, required=False)
    media = serializers.SerializerMethodField()
    can_comment = serializers.BooleanField(required=False, default=True)
    interactions = serializers.SerializerMethodField()
    my_interaction = serializers.SerializerMethodField()
    interaction_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    share_count = serializers.SerializerMethodField()

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user

        if 'can_comment' not in validated_data:
            validated_data['can_comment'] = True

        media_data = validated_data.pop('media', None)
        poll_data = validated_data.pop('poll', None)

        post = Post.objects.create(**validated_data)

        if media_data and isinstance(media_data, dict) and 'file' in media_data:
            PostMedia.objects.create(post=post, file=media_data['file'])
        

        if poll_data and isinstance(poll_data, dict):
            poll = PostPollSerializer(data=poll_data)
            poll.is_valid(raise_exception=True)
            poll.save(post=post)

        return post

    def get_media(self, post):
        return PostMediaSerializer(post.media.filter(is_active=True), many=True).data
    
    def get_my_interaction(self, post):
        user = self.context['request'].user
        try:
            interaction = post.interactions.get(user=user, is_active=True)
            return InteractionChoices(interaction.type).label.lower()
        except Interaction.DoesNotExist:
            return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['post_type'] = PostType(instance.post_type).label.lower()
        return data

    def get_interactions(self, post):
        qs = post.interactions.filter(is_active=True)
        return {
            choice.label.lower(): qs.filter(type=choice.value).count()
            for choice in InteractionChoices
        }
    
    def get_interaction_count(self, post):
        return post.interactions.filter(is_active=True).count()
    
    def get_comment_count(self, post):
        return post.comments.filter(is_active=True).count()
    
    def get_share_count(self, post):
        return post.shares.filter(is_active=True).count()
    
    class Meta:
        model = Post
        fields = [
            'id', 'author', 'post_type', 'can_comment', 'is_shared',
            'shared_post', 'content', 'is_edited', 'created_at', 'updated_at', 
            'media', 'poll', 'interactions','my_interaction',
            'comment_count', 'share_count', 'interaction_count'
        ]
        read_only_fields = [
            'post_type', 'author','is_shared', 'shared_post', 'is_edited', 'interactions', 'created_at', 
            'updated_at', 'my_interaction', 'comment_count', 'share_count'
        ]


class CommentSerializer(serializers.ModelSerializer):
    post = serializers.PrimaryKeyRelatedField(queryset=Post.objects.filter(is_active=True), required=True)
    parent_comment = serializers.PrimaryKeyRelatedField(queryset=Comment.objects.filter(is_active=True), required=False)
    interactions = serializers.SerializerMethodField()
    interaction_count = serializers.SerializerMethodField()
    author = MinimalUserSerializer(read_only=True)
    my_interaction = serializers.SerializerMethodField()

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user


        parent = self.context.get('parent_comment', None)
        if not parent:
            parent = validated_data.get('parent_comment', None)

        if parent and parent.parent_comment:
            validated_data['parent_comment'] = parent.parent_comment
        elif parent:
            validated_data['parent_comment'] = parent

        comment = Comment.objects.create(**validated_data)

        return comment
    
    def save(self, **kwargs):
        parent_comment = kwargs.pop('parent_comment', None)
        if parent_comment:
            self.context['parent_comment'] = parent_comment
        return super().save(**kwargs)

    def to_representation(self, comment):
        data = super().to_representation(comment)
        data['parent_comment'] = comment.parent_comment.id if comment.parent_comment else None

        return data
    
    def get_interactions(self, comment):
        qs = comment.interactions.filter(is_active=True)
        return {
            choice.label.lower(): qs.filter(type=choice.value).count()
            for choice in InteractionChoices
        }
    
    def get_my_interaction(self, comment):
        user = self.context['request'].user
        try:
            interaction = comment.interactions.get(user=user, is_active=True)
            return InteractionChoices(interaction.type).label.lower()
        except Interaction.DoesNotExist:
            return None
        
    def get_interaction_count(self, comment):
        return comment.interactions.filter(is_active=True).count()

    class Meta:
        model = Comment
        fields = [
            'id', 'post', 'author', 'content', 'is_edited', 
            'interactions', 'my_interaction', 'created_at', 'updated_at', 
            'parent_comment', 'interaction_count'
        ]
        read_only_fields = [
            'author', 'is_edited', 'interactions', 'my_interaction', 'created_at', 
            'updated_at'
        ]

class InteractionCreateSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(choices=InteractionChoices.choices)
    post = serializers.PrimaryKeyRelatedField(
        queryset=Post.objects.filter(is_active=True),
        required=False, allow_null=True
    )
    comment = serializers.PrimaryKeyRelatedField(
        queryset=Comment.objects.filter(is_active=True),
        required=False, allow_null=True
    )

    def create(self, validated_data):
        user = self.context['request'].user
        return Interaction.objects.create(user=user, **validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['user'] = MinimalUserSerializer(instance.user, context=self.context).data
        return data
    
    class Meta:
        model = Interaction
        fields = [
            'id', 'type', 'user',
            'post', 'comment'
        ]
        read_only_fields = [
            'id', 'user'
        ]

class InteractionListSerializer(serializers.ModelSerializer):
    reaction = serializers.SerializerMethodField()

    def get_reaction(self, interaction):
        return InteractionChoices(interaction.type).label.lower()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['user'] = MinimalUserSerializer(instance.user, context=self.context).data
        return data

    class Meta:
        model = Interaction
        fields = [
            'id', 'user', 'reaction',
            'created_at'
        ]


class DeviceSerializer(serializers.ModelSerializer):

    def create(self, validated_data):
        user = self.context['request'].user
        obj, _ = Device.objects.update_or_create(
            device_token=validated_data['device_token'],
            defaults={'user': user}
        )
        return obj

    class Meta:
        model = Device
        fields = ['id', 'device_token']
        read_only_fields = ['id']


class NotificationSerializer(serializers.ModelSerializer):
    user = MinimalUserSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'is_read',
            'target_type', 'target_id', 'user', 
            'created_at'
        ]


class ConversationSerializer(serializers.ModelSerializer):
    user1 = MinimalUserSerializer(read_only=True)
    user2 = MinimalUserSerializer(read_only=True)

    class Meta:
        model = Conversation
        fields = [
            'id', 'user1', 'user2',
            'created_at'
        ]


class MessageMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.CharField(source='file.url')

    class Meta:
        model = MessageMedia
        fields = ['id', 'file_url', 'created_at']


class MessageSerializer(serializers.ModelSerializer):
    sender = MinimalUserSerializer(read_only=True)
    receiver = MinimalUserSerializer(read_only=True)
    media = MessageMediaSerializer(many=False, required=False)
    conversation = ConversationSerializer(read_only=True)

    class Meta:
        model = Message
        fields = [
            'id','conversation', 'sender', 'receiver', 'content',
            'media', 'is_read', 'created_at' 
        ]

class GroupSerialzier(serializers.ModelSerializer):
    members = CustomUserSerialzier(read_only=True, many=True)
    member_count = serializers.IntegerField(source='members.count', read_only=True)

    class Meta:
        model = Group
        fields = [
            'id', 'name', 'members', 'member_count'
        ]