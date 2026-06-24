"""Logging strutturato e tracciabile per l'agente."""
import json


def log_event(trace_id: str, event: str, session_id:str, **fields):
    """Scrive UNA riga di log strutturata (JSON), etichettata col
    trace_id."""
    record = {"trace_id": trace_id,"session_id": session_id, "event": event, **fields}
    print(json.dumps(record, ensure_ascii=False))