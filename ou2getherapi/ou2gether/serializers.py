from rest_framework import serializers
from cloudinary.uploader import upload
from cloudinary.utils import cloudinary_url
from ou2gether.models import User, Post, Comment, InteractionChoices, PostMedia, PostPoll, PollOption, CommentMedia


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
        data['cover'] = instance.cover.url if instance.avatar else ''

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
            data['password'] = instance.set_password(data['password'])

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
    id = serializers.IntegerField(required=False)
    votes_count = serializers.IntegerField(source='poll_votes.count', read_only=True)

    class Meta:
        model = PollOption
        fields = ['id', 'content', 'votes_count']


class PostPollSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(many=True)

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
    poll = PostPollSerializer()
    media = PostMediaSerializer(many=True)
    interactions = serializers.SerializerMethodField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['author'] = MinimalUserSerializer(instance.author).data
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
            'id', 'author', 'type', 'is_commendable',
            'content', 'is_edited', 'created_at', 'updated_at', 'media',
            'poll', 'interactions',
        ]
        read_only_fields = [
            'author', 'is_edited', 'interactions', 'created_at', 
            'updated_at'
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

    def create(self, validated_data):
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['parent_comment'] = instance.parent_comment.id if instance.parent_comment else None
        data['author'] = MinimalUserSerializer(instance.author).data

        return data
    
    def get_interactions(self, comment):
        qs = comment.interaction_set.filter(is_active=True)
        return {
            choice.label.lower(): qs.filter(type=choice.value).count()
            for choice in InteractionChoices
        }

    class Meta:
        model = Comment
        fields = [
            'id', 'post', 'author', 'content',
            'media', 'is_edited', 'interactions', 'created_at', 'updated_at', 
            'parent_comment'
        ]
        read_only_fields = [
            'author', 'is_edited', 'interactions', 'created_at', 
            'updated_at'
        ]
