"""
ChatService — orchestrates a full chat turn.

  1. Saves the user message
  2. If RAG mode → retrieves relevant chunks via LangChain RAGService
  3. Builds context (sliding window via ContextManager)
     → injects RAG chunks between system prompt and history
  4. Calls LLM (via LLMService)
  5. Saves assistant reply
  6. If token budget > 80% → summarises old messages and resets history
  7. Returns the assistant Message object
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

# Trigger summarisation when token usage hits 80% of the limit
SUMMARISE_THRESHOLD = 0.8


class ChatService:
    def handle_message(self, conversation: Conversation, user_content: str) -> Message:
        """
        Full chat turn: save user msg → RAG retrieve (if RAG mode)
        → build context → call LLM → save reply → summarise if needed.
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
            rag_context=rag_context,
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
            "Conversation %s — turn complete (%s mode), %d tokens used (total: %d).",
            conversation.id, conversation.mode, tokens_used, conversation.total_tokens_used
        )

        # 7. Summarise if token budget > 80%
        token_limit = settings.CONTEXT_TOKEN_LIMIT
        if conversation.total_tokens_used >= token_limit * SUMMARISE_THRESHOLD:
            self._summarise(conversation)

        return assistant_msg

    def _summarise(self, conversation: Conversation) -> None:
        """
        Summarise the non-summary messages in this conversation.

        Steps:
          1. Fetch all non-summary messages
          2. Ask the LLM to produce a 3-5 sentence summary
          3. Delete all old non-summary messages
          4. Save the summary as a single system message with is_summary=True
          5. Reset conversation.total_tokens_used to the summary's token count
        """
        regular_msgs = list(
            conversation.messages
            .filter(is_summary=False)
            .order_by("created_at", "id")
        )

        if len(regular_msgs) < 4:
            # Not enough messages to be worth summarising
            return

        logger.info(
            "Summarising conversation %s (%d messages, %d tokens used).",
            conversation.id, len(regular_msgs), conversation.total_tokens_used
        )

        # Build the conversation text to summarise
        convo_text = "\n".join(
            f"{m.role.upper()}: {m.content}" for m in regular_msgs
        )

        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "You are a conversation summariser. "
                    "Summarise the following conversation in 3-5 concise sentences, "
                    "capturing the key topics, decisions, and context needed to continue the conversation. "
                    "Write in third person (e.g. 'The user asked about...')."
                ),
            },
            {
                "role": "user",
                "content": f"Summarise this conversation:\n\n{convo_text}",
            },
        ]

        try:
            summary_text, summary_tokens = _llm.chat(summary_prompt)
        except Exception as exc:
            logger.error("Summarisation failed for conversation %s: %s", conversation.id, exc)
            return

        with transaction.atomic():
            # Delete all old non-summary messages
            conversation.messages.filter(is_summary=False).delete()

            # Save the summary as a system message
            Message.objects.create(
                conversation=conversation,
                role=Message.Role.SYSTEM,
                content=f"[SUMMARY OF EARLIER CONVERSATION]\n{summary_text}",
                tokens_used=summary_tokens,
                is_summary=True,
            )

            # Reset token counter to just the summary's size
            conversation.total_tokens_used = summary_tokens
            conversation.save(update_fields=["total_tokens_used", "updated_at"])

        logger.info(
            "Conversation %s summarised — history compressed to %d tokens.",
            conversation.id, summary_tokens
        )
