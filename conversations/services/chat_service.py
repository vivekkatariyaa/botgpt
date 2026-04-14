"""
ChatService — orchestrates a full chat turn.

  1. Saves the user message
  2. If RAG mode → retrieves relevant chunks via LangChain RAGService
  3. Builds context (sliding window via ContextManager)
     → injects RAG chunks between system prompt and history
  4. Calls LLM (via LLMService)
  5. Saves assistant reply
  6. Returns the assistant Message object
"""
import logging
from django.db import transaction
from django.conf import settings

from conversations.models import Conversation, Message
from conversations.services.context_manager import ContextManager
from conversations.services.llm_service import LLMService
from conversations.services.rag_service import RAGService

logger = logging.getLogger(__name__)

_llm     = LLMService()
_rag     = RAGService()
_ctx_mgr = ContextManager(
    max_context_tokens=settings.CONTEXT_TOKEN_LIMIT,
    response_buffer=settings.GROQ_MAX_TOKENS,
)


class ChatService:
    def handle_message(self, conversation: Conversation, user_content: str) -> Message:
        """
        Full chat turn: save user msg → RAG retrieve (if RAG mode)
        → build context → call LLM → save reply.
        Returns the saved assistant Message.
        """
        # 1. Save user message
        with transaction.atomic():
            Message.objects.create(
                conversation=conversation,
                role=Message.Role.USER,
                content=user_content,
            )

        # 2. RAG retrieval — only in RAG mode
        rag_context = ""
        if conversation.mode == Conversation.Mode.RAG:
            rag_context = _rag.retrieve(user_content, str(conversation.id))
            if rag_context:
                logger.info(
                    "RAG: retrieved context for conversation %s (%d chars)",
                    conversation.id, len(rag_context)
                )
            else:
                logger.info(
                    "RAG: no context found for conversation %s — "
                    "answering without document context.",
                    conversation.id
                )

        # 3. Build history list
        history = [
            {
                "role": m.role,
                "content": m.content,
                "is_summary": m.is_summary,
            }
            for m in conversation.messages.order_by("created_at", "id")
        ]

        # 4. Build trimmed context
        #    ContextManager injects rag_context between system prompt and history
        system_prompt = _llm.build_system_prompt(conversation.mode)
        context_messages = _ctx_mgr.build_context(
            system_prompt=system_prompt,
            messages=history,
            rag_context=rag_context,      # ← injected here
        )

        # 5. Call LLM
        reply_text, tokens_used = _llm.chat(context_messages)

        # 6. Save assistant reply + update conversation
        with transaction.atomic():
            assistant_msg = Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=reply_text,
                tokens_used=tokens_used,
            )
            if not conversation.title:
                conversation.title = user_content[:80]
            conversation.total_tokens_used += tokens_used
            conversation.save(update_fields=["title", "total_tokens_used", "updated_at"])

        logger.info(
            "Conversation %s — turn complete (%s mode), %d tokens used.",
            conversation.id, conversation.mode, tokens_used
        )
        return assistant_msg
