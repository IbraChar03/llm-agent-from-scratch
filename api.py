# api.py
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from anthropic import Anthropic
from dotenv import load_dotenv

from agent import rispondi
from observability import log_event
import storage

load_dotenv()
client = Anthropic()
app = FastAPI(title="llm-agent-from-scratch")

storage.init_db()   # crea la tabella conversations se non esiste


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Avvolge OGNI richiesta: genera un request_id e logga metodo/path/status/durata.

    E' come un Filter/Interceptor: gira prima e dopo l'endpoint. Il try/finally
    garantisce il log anche se l'endpoint solleva un'eccezione (status 500).
    """
    request_id = uuid.uuid4().hex[:8]
    request.state.request_id = request_id            # condiviso con handler e agente
    t0 = time.time()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log_event(request_id, "http_request", session_id="-",
                  method=request.method, path=request.url.path,
                  status=status, durata_ms=round((time.time() - t0) * 1000))


@app.exception_handler(Exception)
async def errore_non_gestito(request: Request, exc: Exception):
    """Cattura globale (come @ControllerAdvice): logga l'errore e risponde pulito.

    Il client NON riceve lo stacktrace, solo un 500 con il request_id per correlare.
    """
    request_id = getattr(request.state, "request_id", "-")
    log_event(request_id, "unhandled_error", session_id="-",
              error_type=type(exc).__name__, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": "Errore interno del server", "request_id": request_id},
    )


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
def chat(req: ChatRequest, request: Request):
    messages = storage.load_messages(req.session_id)      # carica la cronologia dal DB
    messages.append({"role": "user", "content": req.message})
    reply = rispondi(messages, client,
                     session_id=req.session_id,
                     approve_fn=nega_scritture,
                     trace_id=request.state.request_id)   # stesso id del log HTTP -> trace unica
    storage.save_messages(req.session_id, messages)       # risalva la cronologia aggiornata
    return ChatResponse(session_id=req.session_id, reply=reply)


@app.delete("/chat/{session_id}")
def delete_chat(session_id: str):
    """Cancella la conversazione (reset / diritto alla cancellazione)."""
    storage.delete_conversation(session_id)
    return {"deleted": session_id}