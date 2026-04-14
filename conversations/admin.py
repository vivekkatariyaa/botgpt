from django.contrib import admin
from .models import Conversation, Message, Document, DocumentChunk


class MessageInline(admin.TabularInline):
    model          = Message
    extra          = 0
    readonly_fields = ['id', 'role', 'tokens_used', 'is_summary', 'created_at']


class DocumentInline(admin.TabularInline):
    model           = Document
    extra           = 0
    readonly_fields = ['id', 'filename', 'status', 'chunk_count', 'created_at']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display  = ['id', 'user', 'title', 'mode', 'total_tokens_used', 'is_active', 'created_at']
    list_filter   = ['mode', 'is_active']
    search_fields = ['title', 'user__username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines       = [MessageInline, DocumentInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display  = ['id', 'conversation', 'role', 'tokens_used', 'is_summary', 'created_at']
    list_filter   = ['role', 'is_summary']
    readonly_fields = ['id', 'created_at']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display  = ['id', 'filename', 'conversation', 'status', 'chunk_count', 'created_at']
    list_filter   = ['status']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display  = ['id', 'document', 'chunk_index', 'embedding_id']
    readonly_fields = ['id', 'created_at']
