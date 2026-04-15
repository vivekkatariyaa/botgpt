"""
LLMService — wraps the Groq API (Llama 3).

Handles:
  - Building the right system prompt per mode
  - Calling the API with retry on transient errors
  - Returning (reply_text, tokens_used)
"""
import logging
from django.conf import settings
from groq import Groq, APIConnectionError, RateLimitError, APIStatusError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self.client     = Groq(api_key=settings.GROQ_API_KEY)
        self.model      = settings.GROQ_MODEL
        self.max_tokens = settings.GROQ_MAX_TOKENS

    @retry(
        retry=retry_if_exception_type((APIConnectionError, RateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def chat(self, messages: list) -> tuple[str, int]:
        """
        Send messages to Groq and return (reply_text, tokens_used).
        Retries up to 3 times on connection/rate-limit errors.
        """
        response = self.client.chat.completions.create(
            model      = self.model,
            messages   = messages,
            max_tokens = self.max_tokens,
            temperature= 0.7,
        )
        reply  = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        logger.info("LLM replied — %d tokens used.", tokens)
        return reply, tokens

    @staticmethod
    def build_system_prompt(mode: str = "open") -> str:
        if mode == "rag":
            return (
                "You are BOTO GPT, a helpful AI assistant in Grounded Chat mode. "
                "Answer questions using ONLY the provided document context. "
                "If the answer is not in the context, clearly say so. "
                "Be concise and accurate."
            )
        return (
            "You are BOTO GPT, a helpful and friendly AI assistant. "
            "Engage naturally, provide accurate information, "
            "and ask clarifying questions when needed."
        )
