from django.contrib.auth.models import User
from rest_framework import status, generics, mixins
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from drf_spectacular.utils import extend_schema

from .models import Conversation, Message, Document
from .services.chat_service import ChatService
from .services.rag_service import RAGService

_chat_service = ChatService()
_rag_service  = RAGService()
from .serializers import (
    ConversationListSerializer,
    ConversationDetailSerializer,
    StartConversationSerializer,
    SendMessageSerializer,
    MessageSerializer,
    DocumentSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)


# ─── Auth ────────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — create user, return token."""
    queryset           = User.objects.all()
    serializer_class   = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {'user': UserSerializer(user).data, 'token': token.key},
            status=status.HTTP_201_CREATED,
        )


class LoginView(ObtainAuthToken):
    """POST /api/auth/login/ — authenticate, return token."""
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': UserSerializer(user).data})


# ─── Conversation ViewSet ─────────────────────────────────────────────────────

class ConversationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user, is_active=True)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationListSerializer

    # POST /api/conversations/
    @extend_schema(request=StartConversationSerializer, responses={201: ConversationDetailSerializer})
    def create(self, request, *args, **kwargs):
        serializer = StartConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        conversation = Conversation.objects.create(
            user  = request.user,
            mode  = serializer.validated_data['mode'],
            title = serializer.validated_data.get('title', ''),
        )

        try:
            _chat_service.handle_message(conversation, serializer.validated_data['first_message'])
        except Exception as exc:
            conversation.delete()
            return Response(
                {'error': 'LLM service unavailable. Please try again.', 'detail': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        conversation.refresh_from_db()
        return Response(ConversationDetailSerializer(conversation).data, status=status.HTTP_201_CREATED)

    # DELETE /api/conversations/{id}/
    def destroy(self, request, *args, **kwargs):
        conversation = self.get_object()
        # Clean up ChromaDB collection if RAG mode
        if conversation.mode == Conversation.Mode.RAG:
            _rag_service.delete_collection(str(conversation.id))
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # POST /api/conversations/{id}/messages/
    @extend_schema(request=SendMessageSerializer, responses={200: MessageSerializer})
    @action(detail=True, methods=['post'], url_path='messages', url_name='send-message')
    def send_message(self, request, pk=None):
        conversation = self.get_object()
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content = serializer.validated_data['content']

        # Per-message character limit (~1000 tokens)
        if len(content) > 4000:
            return Response(
                {'error': 'Message too long. Maximum 4000 characters per message.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            assistant_msg = _chat_service.handle_message(conversation, content)
        except Exception as exc:
            return Response(
                {'error': 'LLM service error. Please try again.', 'detail': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(MessageSerializer(assistant_msg).data, status=status.HTTP_200_OK)

    # GET /api/conversations/{id}/messages/list/
    @extend_schema(responses={200: MessageSerializer(many=True)})
    @action(detail=True, methods=['get'], url_path='messages/list', url_name='list-messages')
    def list_messages(self, request, pk=None):
        conversation = self.get_object()
        messages = conversation.messages.all().order_by('created_at')
        return Response(MessageSerializer(messages, many=True).data)

    # POST /api/conversations/{id}/documents/
    @extend_schema(responses={201: DocumentSerializer})
    @action(detail=True, methods=['post'], url_path='documents', url_name='upload-document',
            parser_classes=[MultiPartParser, FormParser])
    def upload_document(self, request, pk=None):
        conversation = self.get_object()
        file = request.FILES.get('file')

        # Validate file provided
        if not file:
            return Response(
                {'error': 'No file provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file type
        if not file.name.lower().endswith('.pdf'):
            return Response(
                {'error': 'Only PDF files are supported.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file size — max 50 MB
        MAX_SIZE_MB = 50
        if file.size > MAX_SIZE_MB * 1024 * 1024:
            return Response(
                {'error': f'File too large. Maximum allowed size is {MAX_SIZE_MB} MB. '
                          f'Your file is {file.size / (1024*1024):.1f} MB.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate max 3 PDFs per conversation
        MAX_DOCS = 3
        existing_count = conversation.documents.filter(
            status__in=[Document.Status.READY, Document.Status.PROCESSING]
        ).count()
        if existing_count >= MAX_DOCS:
            return Response(
                {'error': f'Maximum {MAX_DOCS} documents allowed per conversation. '
                          f'You already have {existing_count}. '
                          'Delete a document or start a new conversation.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        document = Document.objects.create(
            conversation = conversation,
            filename     = file.name,
            file_path    = file,
            file_size    = file.size,
            status       = Document.Status.PROCESSING,
        )

        # Switch conversation to RAG mode
        Conversation.objects.filter(pk=conversation.pk).update(mode=Conversation.Mode.RAG)

        # Ingest with LangChain RAGService
        try:
            chunk_count = _rag_service.ingest_document(document)
            document.status      = Document.Status.READY
            document.chunk_count = chunk_count
            document.save(update_fields=["status", "chunk_count", "updated_at"])
        except Exception as exc:
            document.status        = Document.Status.FAILED
            document.error_message = str(exc)
            document.save(update_fields=["status", "error_message", "updated_at"])
            return Response(
                {"error": "Document processing failed.", "detail": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)

    # GET /api/conversations/{id}/documents/list/
    @extend_schema(responses={200: DocumentSerializer(many=True)})
    @action(detail=True, methods=['get'], url_path='documents/list', url_name='list-documents')
    def list_documents(self, request, pk=None):
        conversation = self.get_object()
        return Response(DocumentSerializer(conversation.documents.all()).data)
