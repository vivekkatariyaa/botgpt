"""
Unit tests for ContextManager — sliding window token trimming.
No DB, no LLM, no API key needed. Pure logic tests.
"""
from conversations.services.context_manager import ContextManager, count_tokens


class TestCountTokens:
    def test_returns_positive_for_text(self):
        assert count_tokens("Hello world") > 0

    def test_longer_text_has_more_tokens(self):
        short = count_tokens("Hi")
        long  = count_tokens("Hi " * 100)
        assert long > short


class TestContextManager:
    def setup_method(self):
        # Small budget so tests run fast and trimming is easy to trigger
        self.cm = ContextManager(max_context_tokens=300, response_buffer=50)

    def test_system_prompt_is_always_first(self):
        result = self.cm.build_context(
            system_prompt="You are BOT GPT.",
            messages=[{"role": "user", "content": "Hello", "is_summary": False}],
        )
        assert result[0]["role"] == "system"
        assert "BOT GPT" in result[0]["content"]

    def test_empty_history_returns_system_only(self):
        result = self.cm.build_context(
            system_prompt="You are BOT GPT.",
            messages=[],
        )
        assert len(result) == 1
        assert result[0]["role"] == "system"

    def test_rag_context_injected_after_system_prompt(self):
        result = self.cm.build_context(
            system_prompt="You are BOT GPT.",
            messages=[],
            rag_context="Relevant document text here.",
        )
        # Should have system + rag context message
        assert len(result) == 2
        assert "document" in result[1]["content"].lower()

    def test_sliding_window_drops_oldest_messages_when_over_budget(self):
        # 20 long messages — will not all fit in 300 token budget
        many_messages = [
            {"role": "user", "content": "word " * 20, "is_summary": False}
            for _ in range(20)
        ]
        result = self.cm.build_context(
            system_prompt="Short prompt.",
            messages=many_messages,
        )
        history = [m for m in result if m["role"] != "system"]
        # Should be fewer than 20 — trimming worked
        assert len(history) < 20

    def test_most_recent_message_always_kept(self):
        messages = [
            {"role": "user", "content": f"Message number {i}", "is_summary": False}
            for i in range(10)
        ]
        result = self.cm.build_context(
            system_prompt="Short.",
            messages=messages,
        )
        contents = " ".join(m["content"] for m in result)
        assert "Message number 9" in contents

    def test_summary_message_kept_before_regular_history(self):
        messages = [
            {"role": "system", "content": "Earlier summary.", "is_summary": True},
            {"role": "user",   "content": "Latest question.",  "is_summary": False},
        ]
        result = self.cm.build_context(system_prompt="Short.", messages=messages)
        contents = [m["content"] for m in result]
        summary_idx = next(i for i, c in enumerate(contents) if "summary" in c.lower())
        latest_idx  = next(i for i, c in enumerate(contents) if "Latest" in c)
        assert summary_idx < latest_idx
