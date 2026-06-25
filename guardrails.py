"""Guardrail di sicurezza per l'agente: policy sui tool e approvazione umana (W17).

La policy di rischio vive nel CODICE, non nel system prompt: il modello non puo'
modificarla, nemmeno con una prompt injection. La difesa robusta non e' "rilevare"
l'input cattivo (sempre aggirabile), ma "contenere" cio' che l'agente puo' fare:
human-in-the-loop sui tool con side effect.
"""

TOOL_RISK = {
    "controlla_ordine": "read",   # legge -> nessun side effect
    "apri_reclamo": "write",      # scrive -> richiede approvazione
}


def requires_approval(tool_name: str) -> bool:
    """True se il tool ha un side effect e va approvato prima di eseguirlo.

    Default sicuro: un tool SCONOSCIUTO viene trattato come 'write' (in dubbio, nega).
    """
    return TOOL_RISK.get(tool_name, "write") == "write"


def approva_da_cli(tool_name: str, tool_input: dict) -> bool:
    """Chiede conferma umana sulla CLI. Approva SOLO se l'utente scrive 'y'."""
    print("\n[!] Il modello vuole eseguire un'azione con side effect:")
    print(f"    tool:  {tool_name}")
    print(f"    input: {tool_input}")
    risposta = input("    Confermi? [y/N] ").strip().lower()
    return risposta == "y"
