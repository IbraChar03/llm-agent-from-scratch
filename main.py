"""CLI entry point: a multi-turn chat with the agent."""
from anthropic import Anthropic
from dotenv import load_dotenv

from agent import rispondi


def main():
    load_dotenv()                       # read ANTHROPIC_API_KEY from .env if present
    client = Anthropic()
    messages = []                       # conversation memory: persists across turns

    print("Agente ordini attivo. Scrivi un messaggio (o 'esci').\n")
    while True:
        testo = input("Tu:  ").strip()
        if testo.lower() in {"esci", "exit", "quit"}:
            print("Ciao!")
            break
        messages.append({"role": "user", "content": testo})
        risposta = rispondi(messages, client)
        print("Bot:", risposta, "\n")


if __name__ == "__main__":
    main()
