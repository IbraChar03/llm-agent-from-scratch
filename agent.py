"""The agent loop — built from scratch, no framework.

`rispondi` drives a single user turn: it calls the LLM, executes whatever tools
the LLM asks for, feeds the results back, and repeats until the LLM stops
requesting tools (`stop_reason != "tool_use"`) and returns a final text answer.
The conversation history (`messages`) is the agent's short-term memory.
"""
import json
import time

from anthropic import (
    Anthropic,
    APIConnectionError,
    RateLimitError,
    APIStatusError,
)

from tools import TOOLS, execute_tool

MODEL = "claude-haiku-4-5-20251001"


def call_with_retry(client: Anthropic, messages: list, max_tokens: int, max_retries: int = 3):
    """Call the LLM, retrying transient failures with exponential backoff.

    Transient errors (network, 429, 5xx) -> wait and retry.
    Client errors (4xx) -> re-raise immediately (retrying wouldn't help).
    """
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                tools=TOOLS,
                messages=messages,
            )
        except (APIConnectionError, RateLimitError):
            time.sleep(2 ** attempt)          # backoff: 1s, 2s, 4s
        except APIStatusError as e:
            if e.status_code >= 500:
                time.sleep(2 ** attempt)      # 5xx is transient -> retry
            else:
                raise                         # 4xx is on us -> fail fast
    raise RuntimeError(f"LLM unreachable after {max_retries} attempts")


def rispondi(messages: list, client: Anthropic, max_tokens: int = 300) -> str:
    """Run the agent loop for the current conversation and return the final text.

    `messages` is mutated in place: the conversation history grows as the loop runs.
    """
    while True:
        response = call_with_retry(client, messages, max_tokens)
        messages.append({"role": "assistant", "content": response.content})

        # No tool requested -> the LLM is done. Return its final text.
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        # The LLM can request several tools in one response (parallel tool use):
        # execute each and send back one tool_result per request, keyed by tool_use_id.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
                "is_error": "errore" in result,
            })
        messages.append({"role": "user", "content": tool_results})
