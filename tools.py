"""Tools the agent can call: implementations, schemas, and dispatch.

Each tool is a plain Python function. `TOOLS` holds the JSON-Schema descriptions
the Anthropic API needs to know how to call them. `execute_tool` runs a tool by
name, makes the side-effecting one idempotent, and turns any failure into a
result the model can read (instead of crashing the loop).
"""
import json
import hashlib

import storage

# Idempotency store PERSISTENTE (SQLite, vedi storage.py): sopravvive ai riavvii.
# La key e' calcolata sui campi di IDENTITA' stabili dell'operazione, non sul testo libero.

# JSON-Schema descriptions handed to the LLM. The keys (name/description/
# input_schema/type/properties/required) are fixed by the Anthropic API; the
# inner schema is plain JSON-Schema (the same standard OpenAI uses).
TOOLS = [
    {
        "name": "controlla_ordine",
        "description": "Controlla lo stato di un ordine dato il suo ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "ID ordine, es. ORD-123"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "apri_reclamo",
        "description": "Apre un reclamo per un ordine. Ha un side effect (crea un record).",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "ID ordine, es. ORD-123"},
                "motivo": {"type": "string", "description": "Perché il cliente apre il reclamo"},
            },
            "required": ["order_id", "motivo"],
        },
    },
]


def controlla_ordine(order_id: str) -> dict:
    """Read-only: look up an order's status (here a fake DB; in real life a query)."""
    return {"order_id": order_id, "stato": "in consegna", "consegna": "domani"}


def apri_reclamo(order_id: str, motivo: str) -> dict:
    """SIDE EFFECT: open a complaint. Calling it twice would create two complaints,
    which is exactly why it goes through the idempotency check in `execute_tool`."""
    print(f"SIDE EFFECT: aperto reclamo per {order_id} (motivo: {motivo})")
    return {"stato": "reclamo aperto", "order_id": order_id}


def make_idempotency_key(tool_name: str, arguments: dict) -> str:
    """Deterministic fingerprint of (tool_name + arguments).

    Same input -> same key, always (sort_keys makes argument order irrelevant).
    The tool name namespaces the key so the same args to different tools don't collide.
    """
    canonical = json.dumps(arguments, sort_keys=True, default=str)
    raw = f"{tool_name}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def execute_tool(name: str, args: dict) -> dict:
    """Dispatch a tool call by name.

    - `controlla_ordine` is read-only -> just run it.
    - `apri_reclamo` has a side effect -> guard it with an idempotency key so a
      retry/duplicate returns the saved result instead of opening a second complaint.
    - Any exception becomes an {"errore": ...} result so the agent loop never crashes.
    """
    try:
        if name == "controlla_ordine":
            return controlla_ordine(args["order_id"])

        if name == "apri_reclamo":
            # Key sui CAMPI DI IDENTITA' stabili (order_id), NON sul testo libero
            # (motivo): due tentativi dello stesso reclamo scritti diversamente
            # devono contare come UNO.
            key = make_idempotency_key(name, {"order_id": args["order_id"]})
            cached = storage.get_idempotent_result(key)
            if cached is not None:
                return cached                                   # gia' fatto -> result salvato
            result = apri_reclamo(args["order_id"], args["motivo"])
            storage.save_idempotent_result(key, result)         # ricorda (con TTL)
            return result

        return {"errore": f"tool sconosciuto: {name}"}
    except Exception as e:
        return {"errore": str(e)}
