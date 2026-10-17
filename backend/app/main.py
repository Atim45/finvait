import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import config
from .database import (
    get_transaction,
    initialize_database,
    insert_transaction,
    list_transactions,
    list_phone_calls,
    record_inbound_message,
    save_retell_call,
)
from .finance import get_finance_answer
from .local_transcription import LocalWhisperUnavailable, transcribe_local_audio
from .local_speech import LocalSpeechUnavailable, synthesize_speech
from .integrations import (
    check_retell_authorization,
    extract_expense,
    is_authorized_phone_number,
    process_whatsapp_voice,
    transcribe_voice,
    verify_meta_signature,
    verify_retell_webhook,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Voice Finance Demo API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def restrict_cloudflare_tunnel_routes(request: Request, call_next: Any) -> Any:
    if request.headers.get("cf-connecting-ip") and request.url.path not in {
        "/api/retell/finance",
        "/webhooks/retell",
    }:
        return JSONResponse(
            status_code=403,
            content={"detail": "This endpoint is available only from the local demo."},
        )
    return await call_next(request)


class VoiceDemoRequest(BaseModel):
    transcript: str = Field(min_length=2, max_length=1000)


class SpeechDemoRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class AudioDemoResult(BaseModel):
    transcript: str
    extracted: dict[str, Any]
    status: str
    saved: bool
    transaction_id: int | None = None


class CallQuery(BaseModel):
    query: str = Field(min_length=2, max_length=1000)


def save_extracted_demo_expense(
    transcript: str, extracted: dict[str, Any], source: str
) -> dict[str, Any]:
    if extracted["needs_confirmation"]:
        return {
            "status": "needs_confirmation",
            "transcript": transcript,
            "extracted": extracted,
            "saved": False,
        }
    transaction_id, created = insert_transaction(
        {
            **extracted,
            "source": source,
            "source_ref": None,
            "transcript": transcript,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    stored = get_transaction(transaction_id)
    status = (
        "possible_duplicate" if stored and stored["status"] == "possible_duplicate"
        else "saved" if created else "already_saved"
    )
    return {
        "status": status,
        "transaction_id": transaction_id,
        "transcript": transcript,
        "extracted": extracted,
        "saved": True,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "demo" if config.DEMO_MODE else "live",
        "integrations": {
            "whatsapp": bool(config.WHATSAPP_ACCESS_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID),
            "openai": bool(config.OPENAI_API_KEY),
            "retell_function_protection": bool(config.RETELL_FUNCTION_SECRET),
            "retell_webhook": bool(config.RETELL_API_KEY),
            "retell_web_call": bool(config.RETELL_PUBLIC_KEY and config.RETELL_AGENT_ID),
            "caller_allowlist": bool(config.AUTHORIZED_PHONE_NUMBERS),
            "phone_number_configured": bool(config.RETELL_PHONE_NUMBER),
        },
        "public_base_url_configured": bool(config.PUBLIC_BASE_URL),
        "retell_phone_number": config.RETELL_PHONE_NUMBER or None,
        "retell_public_key": config.RETELL_PUBLIC_KEY or None,
        "retell_agent_id": config.RETELL_AGENT_ID or None,
    }


@app.get("/api/transactions")
def transactions() -> list[dict[str, Any]]:
    return list_transactions()


@app.get("/api/calls")
def phone_calls() -> list[dict[str, Any]]:
    return list_phone_calls()


@app.get("/api/transactions/{transaction_id}")
def transaction(transaction_id: int) -> dict[str, Any]:
    result = get_transaction(transaction_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return result


@app.post("/api/demo/process-voice")
def process_voice_demo(payload: VoiceDemoRequest) -> dict[str, Any]:
    if not config.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is required to extract an expense from a transcript",
        )
    try:
        extracted = extract_expense(payload.transcript)
    except Exception as error:
        logger.error("Demo transcript extraction failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Expense extraction provider failed") from error
    return save_extracted_demo_expense(payload.transcript, extracted, "demo_transcript")


@app.post("/api/demo/transcribe-audio")
async def transcribe_audio_locally(
    request: Request,
    mime_type: str = Query(min_length=1, max_length=100),
) -> dict[str, str]:
    normalized_mime = mime_type.split(";", 1)[0].strip().lower()
    allowed_mime_types = {
        "audio/aac",
        "audio/flac",
        "audio/m4a",
        "audio/mp3",
        "audio/mpeg",
        "audio/mp4",
        "audio/mpga",
        "audio/ogg",
        "audio/opus",
        "audio/wav",
        "audio/webm",
        "audio/x-m4a",
        "audio/x-wav",
    }
    if normalized_mime not in allowed_mime_types:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 20 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Audio must be 20 MB or smaller")
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid content length") from error
    audio = await request.body()
    if not audio or len(audio) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413 if audio else 400, detail="Audio is empty or exceeds 20 MB")
    try:
        transcript = await run_in_threadpool(
            transcribe_local_audio,
            audio,
            normalized_mime,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LocalWhisperUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.error("Local Whisper transcription failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Local Whisper transcription failed") from error
    return {
        "transcript": transcript,
        "engine": "faster-whisper",
        "model": config.LOCAL_WHISPER_MODEL,
    }


@app.post("/api/demo/speech")
async def generate_local_speech(payload: SpeechDemoRequest) -> Response:
    try:
        audio = await run_in_threadpool(synthesize_speech, payload.text)
    except LocalSpeechUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Content-Disposition": 'inline; filename="finvait-response.wav"'},
    )


@app.get("/api/demo/speech")
async def generate_linked_local_speech(
    text: str = Query(min_length=1, max_length=500),
) -> Response:
    try:
        audio = await run_in_threadpool(synthesize_speech, text)
    except LocalSpeechUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Content-Disposition": 'inline; filename="finvait-response.wav"'},
    )


@app.post("/api/demo/process-audio", response_model=AudioDemoResult)
async def process_audio_demo(
    request: Request,
    mime_type: str = Query(min_length=1, max_length=100),
) -> dict[str, Any]:
    normalized_mime = mime_type.split(";", 1)[0].strip().lower()
    allowed_mime_types = {
        "audio/aac",
        "audio/flac",
        "audio/m4a",
        "audio/mp3",
        "audio/mpeg",
        "audio/mp4",
        "audio/mpga",
        "audio/ogg",
        "audio/opus",
        "audio/wav",
        "audio/webm",
        "audio/x-m4a",
        "audio/x-wav",
    }
    if normalized_mime not in allowed_mime_types:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    if not config.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is required for audio transcription")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 20 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Audio must be 20 MB or smaller")
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid content length") from error
    audio = await request.body()
    if not audio or len(audio) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413 if audio else 400, detail="Audio is empty or exceeds 20 MB")
    try:
        transcript = transcribe_voice(audio, normalized_mime)
        extracted = extract_expense(transcript)
    except Exception as error:
        logger.error("Demo audio processing failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Audio transcription or extraction provider failed") from error
    return save_extracted_demo_expense(transcript, extracted, "demo_audio_upload")


@app.get("/webhooks/whatsapp")
def whatsapp_verify(
    mode: str | None = Query(default=None, alias="hub.mode"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
) -> PlainTextResponse:
    if (
        mode == "subscribe"
        and challenge
        and config.WHATSAPP_VERIFY_TOKEN
        and verify_token == config.WHATSAPP_VERIFY_TOKEN
    ):
        return PlainTextResponse(content=challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    raw_body = await request.body()
    if not verify_meta_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error
    queued = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                sender = message.get("from")
                if message.get("type") not in {"audio", "voice"} or not sender:
                    continue
                if not is_authorized_phone_number(sender):
                    logger.warning("Ignored WhatsApp voice note from an unauthorized sender")
                    continue
                message_id = message.get("id")
                if not message_id:
                    continue
                if record_inbound_message(message_id, sender):
                    background_tasks.add_task(process_whatsapp_voice, message, sender)
                    queued += 1
    return {"status": "accepted", "queued": str(queued)}


@app.post("/api/retell/finance")
async def retell_finance(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    if not check_retell_authorization(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")
    call = payload.get("call") or {}
    if not isinstance(call, dict):
        raise HTTPException(status_code=403, detail="Call context is not authorized")
    if call.get("call_type") == "web_call":
        # The Retell custom-function bearer secret is required above; browser calls
        # do not have a PSTN caller number to validate.
        pass
    elif not is_authorized_phone_number(call.get("from_number")):
        raise HTTPException(status_code=403, detail="Caller is not authorized")
    arguments = payload.get("args", payload.get("arguments", {}))
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    query = (
        arguments.get("query")
        or payload.get("query")
        or payload.get("transcript")
        or "How much did I spend this month?"
    )
    if not isinstance(query, str) or len(query) > 1000:
        raise HTTPException(status_code=422, detail="Invalid query")
    answer = get_finance_answer(query)
    # Retell custom functions consume a JSON result; keep every value grounded in SQLite.
    return {
        "result": answer["answer"],
        "structured_data": answer,
        "call_id": call.get("call_id", payload.get("call_id")),
    }


@app.post("/webhooks/retell")
async def retell_webhook(
    request: Request,
    x_retell_signature: str | None = Header(default=None),
) -> dict[str, str]:
    raw_body = await request.body()
    if not verify_retell_webhook(raw_body, x_retell_signature):
        raise HTTPException(status_code=401, detail="Invalid Retell webhook signature")
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")
    event = payload.get("event")
    call = payload.get("call")
    if event not in {"call_started", "call_ended", "call_analyzed"}:
        return {"status": "ignored"}
    if not isinstance(call, dict):
        raise HTTPException(status_code=400, detail="Missing Retell call object")
    is_inbound_phone_call = (
        call.get("call_type") == "phone_call" and call.get("direction") == "inbound"
    )
    is_browser_web_call = call.get("call_type") == "web_call"
    if not (is_inbound_phone_call or is_browser_web_call):
        return {"status": "ignored"}
    if is_inbound_phone_call and not is_authorized_phone_number(call.get("from_number")):
        logger.warning("Ignored Retell call webhook from an unauthorized caller")
        return {"status": "ignored"}
    try:
        save_retell_call(call, event)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"status": "processed"}


@app.post("/api/demo/call-query")
def call_query(payload: CallQuery) -> dict[str, Any]:
    return get_finance_answer(payload.query)


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def frontend() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/listen.html", include_in_schema=False)
    def audio_listening_page() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "listen.html")
