"""
ContextManager — sliding window token trimming.

Builds the message list sent to the LLM, keeping it within
the token budget by dropping oldest messages first.
"""
import tiktoken


def count_tokens(text: str) -> int:
    """Count tokens in a string using cl100k_base encoding (used by most models)."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


class ContextManager:
    def __init__(self, max_context_tokens: int = 6000, response_buffer: int = 1024):
        self.available_tokens = max_context_tokens - response_buffer

    def build_context(self, system_prompt: str, messages: list, rag_context: str = "") -> list:
        """
        Returns the final message list to send to the LLM.

        Order:
          1. System prompt  (always included)
          2. RAG context    (injected if RAG mode)
          3. Summary msg    (if exists, replaces old history)
          4. Recent msgs    (sliding window — newest kept, oldest dropped)
        """
        budget = self.available_tokens

        # 1. System prompt — always first
        system_msg = {"role": "system", "content": system_prompt}
        budget -= count_tokens(system_prompt)

        # 2. RAG context — injected as a separate system message
        rag_msg = None
        if rag_context:
            rag_text = f"Relevant context from uploaded documents:\n\n{rag_context}"
            rag_msg = {"role": "system", "content": rag_text}
            budget -= count_tokens(rag_text)

        # 3. Separate summary messages from regular messages
        summary_msgs = [m for m in messages if m.get("is_summary")]
        regular_msgs = [m for m in messages if not m.get("is_summary")]

        # Keep summary messages (they replace large history)
        kept_summaries = []
        for sm in summary_msgs:
            cost = count_tokens(sm["content"])
            if budget - cost >= 0:
                kept_summaries.append({"role": sm["role"], "content": sm["content"]})
                budget -= cost

        # 4. Sliding window — include most recent messages that fit
        kept_history = []
        for msg in reversed(regular_msgs):
            cost = count_tokens(msg["content"])
            if budget - cost >= 0:
                kept_history.insert(0, {"role": msg["role"], "content": msg["content"]})
                budget -= cost
            else:
                break  # stop — older messages won't fit

        # Assemble final list
        result = [system_msg]
        if rag_msg:
            result.append(rag_msg)
        result.extend(kept_summaries)
        result.extend(kept_history)
        return result
