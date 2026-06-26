"""Persistenza delle conversazioni su SQLite: il session store durevole (W18 - G2).

Sostituisce il dict in RAM: le conversazioni sopravvivono ai riavvii del server.
E' la versione minima del pattern di produzione (caricare/salvare la cronologia
da un DB per session_id), con SQLite al posto di Postgres/Redis.
"""
import json
import sqlite3

DB_PATH = "conversations.db"


def _connect() -> sqlite3.Connection:
    # Una connessione nuova per ogni operazione: FastAPI serve le richieste su
    # piu' thread, e una connessione sqlite va usata nel thread che l'ha creata.
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Crea le tabelle se non esistono. Da chiamare una volta all'avvio."""
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS conversations (
                   session_id TEXT PRIMARY KEY,
                   messages   TEXT NOT NULL,
                   updated_at TEXT NOT NULL DEFAULT (datetime('now'))
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS idempotency_keys (
                   key        TEXT PRIMARY KEY,
                   result     TEXT NOT NULL,
                   expires_at TEXT NOT NULL
               )"""
        )
        conn.commit()
    finally:
        conn.close()


def _to_jsonable(o):
    """I content block dell'SDK Anthropic sono modelli pydantic -> dict.

    json.dumps chiama questa funzione su ogni oggetto che non sa serializzare.
    """
    if hasattr(o, "model_dump"):
        return o.model_dump(exclude_none=True)   # niente campi None (es. citations) -> reload pulito
    raise TypeError(f"Non serializzabile: {type(o)}")


def load_messages(session_id: str) -> list:
    """Carica la cronologia di una sessione (lista vuota se e' nuova)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    return json.loads(row[0]) if row else []


def save_messages(session_id: str, messages: list) -> None:
    """Salva (upsert) la cronologia aggiornata della sessione."""
    blob = json.dumps(messages, default=_to_jsonable, ensure_ascii=False)
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO conversations (session_id, messages, updated_at)
                   VALUES (?, ?, datetime('now'))
               ON CONFLICT(session_id) DO UPDATE SET
                   messages   = excluded.messages,
                   updated_at = excluded.updated_at""",
            (session_id, blob),
        )
        conn.commit()
    finally:
        conn.close()


def delete_conversation(session_id: str) -> None:
    """Cancella una conversazione (reset / diritto alla cancellazione)."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def get_idempotent_result(key: str):
    """Ritorna il result salvato per questa key se esiste e NON e' scaduto, sennò None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT result FROM idempotency_keys WHERE key = ? AND expires_at > datetime('now')",
            (key,),
        ).fetchone()
    finally:
        conn.close()
    return json.loads(row[0]) if row else None


def save_idempotent_result(key: str, result: dict, ttl_seconds: int = 86400) -> None:
    """Salva il result per questa key con una scadenza (TTL, default 24h)."""
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO idempotency_keys (key, result, expires_at)
                   VALUES (?, ?, datetime('now', ?))
               ON CONFLICT(key) DO UPDATE SET
                   result     = excluded.result,
                   expires_at = excluded.expires_at""",
            (key, json.dumps(result, ensure_ascii=False), f"+{ttl_seconds} seconds"),
        )
        conn.commit()
    finally:
        conn.close()
