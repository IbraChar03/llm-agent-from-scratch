"""CLI entry point: a multi-turn chat with the agent."""
from anthropic import Anthropic
from dotenv import load_dotenv

from agent import rispondi
import storage
import uuid

def main():
    load_dotenv()                       # read ANTHROPIC_API_KEY from .env if present
    storage.init_db()                   # assicura le tabelle (idempotency / conversazioni)
    client = Anthropic()
    messages = []                       # conversation memory: persists across turns
    session_id = uuid.uuid4().hex[:8]  
    print("Agente ordini attivo. Scrivi un messaggio (o 'esci').\n")
    while True:
        testo = input("Tu:  ").strip()
        if testo.lower() in {"esci", "exit", "quit"}:
            print("Ciao!")
            break
        messages.append({"role": "user", "content": testo})
        risposta = rispondi(messages, client,session_id=session_id)
        print("Bot:", risposta, "\n")


if __name__ == "__main__":
    main()
