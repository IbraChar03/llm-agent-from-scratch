# api.py
from fastapi import FastAPI
from pydantic import BaseModel
from anthropic import Anthropic
from dotenv import load_dotenv

from agent import rispondi
import storage

load_dotenv()
client = Anthropic()
app = FastAPI(title="llm-agent-from-scratch")

storage.init_db()   # crea la tabella conversations se non esiste


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str


def nega_scritture(tool_name: str, tool_input: dict) -> bool:
    """approve_fn per l'HTTP: niente input() -> nega le azioni con side effect."""
    return False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    messages = storage.load_messages(req.session_id)      # carica la cronologia dal DB
    messages.append({"role": "user", "content": req.message})
    reply = rispondi(messages, client,
                     session_id=req.session_id,
                     approve_fn=nega_scritture)
    storage.save_messages(req.session_id, messages)       # risalva la cronologia aggiornata
    return ChatResponse(session_id=req.session_id, reply=reply)


@app.delete("/chat/{session_id}")
def delete_chat(session_id: str):
    """Cancella la conversazione (reset / diritto alla cancellazione)."""
    storage.delete_conversation(session_id)
    return {"deleted": session_id}