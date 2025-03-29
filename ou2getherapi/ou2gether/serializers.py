from rest_framework.serializers import ModelSerializer
from ou2gether.models import User

class UserSerializer(ModelSerializer):
    def to_representation(self, instance):
        return super().to_representation(instance)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']
    
    def create(self, validated_data):
        data = validated_data.copy()

        user = User(**data)
        user.set_password(data["password"])
        user.save()

        return user
    

class UserCoverSerializer(ModelSerializer):
    pass


class UserAvatarSerializer(ModelSerializer):
    pass


class PostSerializer(ModelSerializer):
    pass


class PostMediaSerializer(ModelSerializer):
    pass


class PostPollSerializer(ModelSerializer):
    pass


class PostPollOptionSerializer(ModelSerializer):
    pass


class PostPollVoteSerializer(ModelSerializer):
    pass


class CommentSerializer(ModelSerializer):
    pass


class CommentMediaSerializer(ModelSerializer):
    pass


class ShareSerializer(ModelSerializer):
    pass


class FollowSerializer(ModelSerializer):
    pass


class BlockSerializer(ModelSerializer):
    pass