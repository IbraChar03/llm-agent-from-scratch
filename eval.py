"""Eval harness: run golden inputs through the real agent and score the outputs.

Uses a 'contains' matcher because the agent's answer is free text. Calls the real
API (a few cents, non-deterministic) — the realistic way to evaluate an LLM system.
Re-run after any change: a drop in pass_rate flags a regression before it ships.
"""
from anthropic import Anthropic
from dotenv import load_dotenv

from agent import rispondi

GOLDEN = [
    {"input": "com'è il mio ordine ORD-123?",                    "atteso": "consegna"},
    {"input": "apri un reclamo per ORD-123 perché è in ritardo", "atteso": "reclamo"},
    {"input": "quando arriva il mio ordine ORD-555?",            "atteso": "domani"},
]


def run_eval() -> float:
    load_dotenv()
    client = Anthropic()
    promossi = 0
    for caso in GOLDEN:
        messages = [{"role": "user", "content": caso["input"]}]   # fresh conversation per case
        risposta = rispondi(messages, client)
        if caso["atteso"].lower() in risposta.lower():            # 'contains' matcher
            promossi += 1
        else:
            print("FALLITO:", caso["input"], "->", risposta)
    pass_rate = promossi / len(GOLDEN)
    print(f"pass_rate = {promossi}/{len(GOLDEN)} = {pass_rate:.2f}")
    return pass_rate


if __name__ == "__main__":
    run_eval()
