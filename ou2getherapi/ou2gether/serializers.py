from rest_framework import serializers
from ou2gether.models import (
    User, Post, Comment, Interaction, Notification, Message,
    PostMedia, PostPoll, PollOption, CommentMedia, InteractionChoices, 
    PostType, MessageMedia, Device, Conversation
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 
            'member_id', 'avatar', 'cover', 'bio', 
            'is_verified'
        ]
        extra_kwargs = {
            'password': {
                'write_only': True
            }
        }
    
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


class MinimalUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'avatar']


class PostMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.CharField(source='file.url')
    

    class Meta:
        model = PostMedia
        fields = ['id', 'file_url', 'created_at']


class PollOptionSerializer(serializers.ModelSerializer):
    votes_count = serializers.IntegerField(source='poll_votes.count', read_only=True)

    class Meta:
        model = PollOption
        fields = ['id', 'content', 'votes_count']


class PostPollSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(many=True)

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
                    option = instance.polloption_set.get(id=option_id)
                    option.content = option_data.get('content', option.content)
                    option.save()
                    new_option_ids.append(option_id)
                except PollOption.DoesNotExist:
                    continue
            else:
                new_option = PollOption.objects.create(post_poll=instance, **option_data)
                new_option_ids.append(new_option.id)

        instance.polloption_set.exclude(id__in=new_option_ids).delete()

        return instance
    
    class Meta:
        model = PostPoll
        fields = ['id', 'question', 'options']



class PostSerializer(serializers.ModelSerializer):
    author = MinimalUserSerializer(read_only=True)
    # poll = serializers.SerializerMethodField()
    poll = PostPollSerializer(many=False, required=False)
    media = serializers.SerializerMethodField()
    interactions = serializers.SerializerMethodField()
    my_interaction = serializers.SerializerMethodField()

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user

        media_data = validated_data.pop('media', None)
        poll_data = validated_data.pop('poll', None)

        post = Post.objects.create(**validated_data)

        if media_data and isinstance(media_data, dict) and 'file' in media_data:
            PostMedia.objects.create(post=post, file=media_data['file'])
        
        if 'is_commendable' not in validated_data:
            validated_data['is_commendable'] = True

        if poll_data and isinstance(poll_data, dict):
            poll = PostPollSerializer(data=poll_data)
            poll.is_valid(raise_exception=True)
            poll.save(post=post)

        return post

    # def get_poll(self, post):
    #     if hasattr(post, 'poll'):
    #         return PostPollSerializer(post.poll, context=self.context).data
    #     return None

    def get_media(self, post):
        return PostMediaSerializer(post.media.filter(is_active=True).all(), many=True).data
    
    def get_my_interaction(self, post):
        user = self.context['request'].user
        try:
            interaction = post.interaction_set.get(user=user, is_active=True)
            return InteractionChoices(interaction.type).label.lower()
        except Interaction.DoesNotExist:
            return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['post_type'] = PostType(instance.post_type).label.lower()
        return data

    def get_interactions(self, post):
        qs = post.interaction_set.filter(is_active=True)
        return {
            choice.label.lower(): qs.filter(type=choice.value).count()
            for choice in InteractionChoices
        }
    
    class Meta:
        model = Post
        fields = [
            'id', 'author', 'post_type', 'is_commendable', 'is_shared',
            'shared_post', 'content', 'is_edited', 'created_at', 'updated_at', 
            'media', 'poll', 'interactions','my_interaction'
        ]
        read_only_fields = [
            'post_type', 'author','is_shared', 'shared_post', 'is_edited', 'interactions', 'created_at', 
            'updated_at', 'my_interaction'
        ]


class CommentMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.CharField(source='file.url')

    class Meta:
        model = CommentMedia
        fields = ['id', 'file_url', 'created_at']


class CommentSerializer(serializers.ModelSerializer):
    post = serializers.PrimaryKeyRelatedField(queryset=Post.objects.filter(is_active=True), required=True)
    parent_comment = serializers.PrimaryKeyRelatedField(queryset=Comment.objects.filter(is_active=True), required=False)
    media = CommentMediaSerializer(many=False, required=False)
    interactions = serializers.SerializerMethodField()
    author = MinimalUserSerializer(read_only=True)
    my_interaction = serializers.SerializerMethodField()

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user

        media_data = validated_data.pop('media', None)

        parent = self.context.get('parent_comment', None)
        if not parent:
            parent = validated_data.get('parent_comment', None)

        if parent and parent.parent_comment:
            validated_data['parent_comment'] = parent.parent_comment
        elif parent:
            validated_data['parent_comment'] = parent

        comment = Comment.objects.create(**validated_data)

        if media_data and isinstance(media_data, dict) and 'file' in media_data:
            CommentMedia.objects.create(comment=comment, file=media_data['file'])

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
        qs = comment.interaction_set.filter(is_active=True)
        return {
            choice.label.lower(): qs.filter(type=choice.value).count()
            for choice in InteractionChoices
        }
    
    def get_my_interaction(self, comment):
        user = self.context['request'].user
        try:
            interaction = comment.interaction_set.get(user=user, is_active=True)
            return InteractionChoices(interaction.type).label.lower()
        except Interaction.DoesNotExist:
            return None

    class Meta:
        model = Comment
        fields = [
            'id', 'post', 'author', 'content',
            'media', 'is_edited', 'interactions', 'my_interaction', 'created_at', 'updated_at', 
            'parent_comment'
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
        data['user'] = MinimalUserSerializer(instance.user).data
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
        data['user'] = MinimalUserSerializer(instance.user).data
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