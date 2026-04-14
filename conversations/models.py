import uuid
from django.db import models
from django.contrib.auth.models import User


class Conversation(models.Model):
    class Mode(models.TextChoices):
        OPEN = 'open', 'Open Chat'
        RAG  = 'rag',  'RAG / Grounded Chat'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user             = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title            = models.CharField(max_length=255, blank=True, default='')
    mode             = models.CharField(max_length=10, choices=Mode.choices, default=Mode.OPEN)
    is_active        = models.BooleanField(default=True)
    total_tokens_used = models.PositiveIntegerField(default=0)
    summary          = models.TextField(blank=True, default='')
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} | {self.title or self.id} ({self.mode})"


class Message(models.Model):
    class Role(models.TextChoices):
        USER      = 'user',      'User'
        ASSISTANT = 'assistant', 'Assistant'
        SYSTEM    = 'system',    'System'

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role         = models.CharField(max_length=20, choices=Role.choices)
    content      = models.TextField()
    tokens_used  = models.PositiveIntegerField(default=0)
    is_summary   = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING    = 'pending',    'Pending'
        PROCESSING = 'processing', 'Processing'
        READY      = 'ready',      'Ready'
        FAILED     = 'failed',     'Failed'

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation  = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='documents')
    filename      = models.CharField(max_length=255)
    file_path     = models.FileField(upload_to='documents/%Y/%m/%d/')
    file_size     = models.PositiveIntegerField(default=0)
    status        = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    chunk_count   = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} ({self.status})"


class DocumentChunk(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document     = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    chunk_text   = models.TextField()
    chunk_index  = models.PositiveIntegerField()
    embedding_id = models.CharField(max_length=255, blank=True, default='')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chunk_index']
        unique_together = [('document', 'chunk_index')]

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document.filename}"
