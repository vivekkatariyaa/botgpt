"""
Unit tests for LLMService.
All Groq API calls are mocked — no real API key needed.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestSystemPrompt:
    def test_open_mode_prompt_contains_bot_gpt(self):
        from conversations.services.llm_service import LLMService
        prompt = LLMService.build_system_prompt("open")
        assert "BOT GPT" in prompt

    def test_rag_mode_prompt_mentions_context(self):
        from conversations.services.llm_service import LLMService
        prompt = LLMService.build_system_prompt("rag")
        assert "context" in prompt.lower()

    def test_open_and_rag_prompts_are_different(self):
        from conversations.services.llm_service import LLMService
        assert LLMService.build_system_prompt("open") != LLMService.build_system_prompt("rag")


class TestLLMServiceChat:
    @patch("conversations.services.llm_service.Groq")
    def test_chat_returns_reply_and_token_count(self, mock_groq_class):
        # Arrange mock
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "Python is a programming language."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.total_tokens = 50
        mock_client.chat.completions.create.return_value = mock_response

        from conversations.services.llm_service import LLMService
        service = LLMService()
        reply, tokens = service.chat([{"role": "user", "content": "What is Python?"}])

        assert reply == "Python is a programming language."
        assert tokens == 50

    @patch("conversations.services.llm_service.Groq")
    def test_chat_calls_api_with_correct_messages(self, mock_groq_class):
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "reply"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.total_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response

        from conversations.services.llm_service import LLMService
        service   = LLMService()
        messages  = [{"role": "user", "content": "Hello"}]
        service.chat(messages)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["messages"] == messages
