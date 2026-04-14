from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Conversation, Message, Document


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model  = User
        fields = ['id', 'username', 'email', 'password']

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'username', 'email']


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model        = Message
        fields       = ['id', 'role', 'content', 'tokens_used', 'is_summary', 'created_at']
        read_only_fields = fields


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Document
        fields = ['id', 'filename', 'file_size', 'status', 'chunk_count', 'error_message', 'created_at']
        read_only_fields = fields


class ConversationListSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model  = Conversation
        fields = ['id', 'title', 'mode', 'is_active', 'total_tokens_used', 'message_count', 'created_at', 'updated_at']

    def get_message_count(self, obj) -> int:
        return obj.messages.count()


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages  = MessageSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)

    class Meta:
        model  = Conversation
        fields = ['id', 'title', 'mode', 'is_active', 'total_tokens_used', 'summary', 'messages', 'documents', 'created_at', 'updated_at']


class StartConversationSerializer(serializers.Serializer):
    first_message = serializers.CharField(min_length=1, max_length=8000)
    mode          = serializers.ChoiceField(choices=Conversation.Mode.choices, default=Conversation.Mode.OPEN)
    title         = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(min_length=1, max_length=8000)
