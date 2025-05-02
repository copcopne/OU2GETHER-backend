from rest_framework import serializers
from ou2gether.models import User, Post, InteractionChoices, PostMedia, PostPoll, PollOption, PostChoices


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'avatar', 'cover', 'bio', 'is_verified']
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


class PostMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.CharField(source='file.url', read_only=True)

    class Meta:
        model = PostMedia
        fields = ['id', 'file_url', 'created_at']


class PollOptionSerializer(serializers.ModelSerializer):
    votes_count = serializers.IntegerField(source='pollvote_set.count', read_only=True)

    class Meta:
        model = PollOption
        fields = ['id', 'content', 'votes_count']


class PostPollSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(source='polloption_set', many=True, read_only=True)

    class Meta:
        model = PostPoll
        fields = ['id', 'question', 'options']


class PostSerializer(serializers.ModelSerializer):
    media = PostMediaSerializer(source='post_media', many=True, read_only=True)
    poll = PostPollSerializer(source='postpoll_set', many=False, read_only=True)
    interactions = serializers.SerializerMethodField()

    def get_interactions(self, post):
        # request = self.context.get('request')
        qs = post.interaction_set.filter(is_active=True)
        return {
            choice.label.lower(): qs.filter(type=choice.value).count()
            for choice in InteractionChoices
        }

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'type', 'is_commendable',
            'content', 'created_at', 'updated_at',
            'media',
            'poll',
            'interactions',
        ]


class PostPollVoteSerializer(serializers.ModelSerializer):
    pass


class CommentSerializer(serializers.ModelSerializer):
    pass


class CommentMediaSerializer(serializers.ModelSerializer):
    pass


class ShareSerializer(serializers.ModelSerializer):
    pass


class InteractionSerializer(serializers.ModelSerializer):
    pass


class FollowSerializer(serializers.ModelSerializer):
    pass


class BlockSerializer(serializers.ModelSerializer):
    pass