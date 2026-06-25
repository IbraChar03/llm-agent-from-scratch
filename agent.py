"""The agent loop — built from scratch, no framework.

`rispondi` drives a single user turn: it calls the LLM, executes whatever tools
the LLM asks for, feeds the results back, and repeats until the LLM stops
requesting tools (`stop_reason != "tool_use"`) and returns a final text answer.
The conversation history (`messages`) is the agent's short-term memory.
"""
import json
import time
import uuid
from observability import log_event

from anthropic import (
    Anthropic,
    APIConnectionError,
    RateLimitError,
    APIStatusError,
)

from tools import TOOLS, execute_tool
from guardrails import requires_approval, approva_da_cli

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


def rispondi(messages: list, client: Anthropic, max_tokens: int = 300,
             session_id: str = "", approve_fn=None) -> str:
    """Run the agent loop for the current conversation and return the final text.

    `messages` is mutated in place: the conversation history grows as the loop runs.
    `approve_fn(tool_name, tool_input) -> bool` decides whether a side-effect tool may
    run; defaults to a CLI y/N prompt. Tests can inject an auto-approve/deny function.
    """
    if approve_fn is None:
        approve_fn = approva_da_cli

    trace_id = uuid.uuid4().hex[:8]
    log_event(trace_id, "request_start",session_id=session_id)

    t_start = time.time()
    token_totali = 0
    costo_totale = 0.0
    giri = 0
    tool_totali = 0

    while True:
        t0 = time.time()
        response = call_with_retry(client, messages, max_tokens)
        durata_ms = round((time.time() - t0) * 1000)

        u = response.usage
        costo_eur = round(((u.input_tokens / 1_000_000) * 1.00
                             + (u.output_tokens / 1_000_000) * 5.00) * 0.92,6)
        log_event(trace_id, "llm_call", session_id=session_id,
                    durata_ms=durata_ms,
                    token_in=u.input_tokens,
                    token_out=u.output_tokens,
                    costo_eur=costo_eur)

        giri += 1
        token_totali += u.input_tokens + u.output_tokens
        costo_totale += costo_eur

        messages.append({"role": "assistant", "content": response.content})

        # No tool requested -> the LLM is done. Return its final text.
        if response.stop_reason != "tool_use":
            log_event(trace_id, "request_end", session_id=session_id,
                      giri=giri,
                      tool_totali=tool_totali,
                      token_totali=token_totali,
                      costo_totale_eur=round(costo_totale, 6),
                      durata_totale_ms=round((time.time() - t_start) * 1000))
            return "".join(b.text for b in response.content if b.type == "text")

        # The LLM can request several tools in one response (parallel tool use):
        # execute each and send back one tool_result per request, keyed by tool_use_id.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            # --- Guardrail W17: human approval gate on side-effect tools ---
            # The risk policy lives in code (guardrails.py), not in the prompt, so a
            # prompt injection cannot talk its way past it.
            if requires_approval(block.name):
                log_event(trace_id, "approval_requested", session_id=session_id,
                          tool=block.name, reason="tool_has_side_effect")
                approvato = approve_fn(block.name, block.input)
                log_event(trace_id, "approval_result", session_id=session_id,
                          tool=block.name, approved=approvato)
                if not approvato:
                    log_event(trace_id, "tool_blocked", session_id=session_id,
                              tool=block.name, reason="approval_denied")
                    # The API requires a tool_result for EVERY tool_use, even when we
                    # refuse to run it -> return an error result instead of executing.
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"errore": "azione non autorizzata dall'utente"}),
                        "is_error": True,
                    })
                    continue
            # --- end guardrail ---

            t0 = time.time()
            result = execute_tool(block.name, block.input)
            durata_ms = round((time.time() - t0) * 1000)
            log_event(trace_id, "tool_call", session_id=session_id,
                        tool=block.name, durata_ms=durata_ms,
                        esito="errore" if "errore" in result else "ok")
            
            tool_totali += 1
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
                "is_error": "errore" in result,
            })
        messages.append({"role": "user", "content": tool_results})
