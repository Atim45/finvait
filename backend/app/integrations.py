import hashlib
import hmac
import io
import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Any

import httpx
from openai import OpenAI

from . import config
from .database import get_transaction, insert_transaction, update_inbound_message

logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 20 * 1024 * 1024


def verify_meta_signature(raw_body: bytes, signature: str | None) -> bool:
    if not config.WHATSAPP_APP_SECRET:
        return config.DEMO_MODE and not config.WHATSAPP_ACCESS_TOKEN
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        config.WHATSAPP_APP_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), expected)


def _whatsapp_headers() -> dict[str, str]:
    if not config.WHATSAPP_ACCESS_TOKEN:
        raise RuntimeError("WhatsApp access token is not configured")
    return {"Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}"}


def _download_whatsapp_audio(media_id: str) -> tuple[bytes, str]:
    base = f"https://graph.facebook.com/{config.WHATSAPP_GRAPH_API_VERSION}"
    with httpx.Client(timeout=30) as client:
        metadata_response = client.get(
            f"{base}/{media_id}", headers=_whatsapp_headers()
        )
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        mime_type = metadata.get("mime_type", "")
        if not mime_type.startswith("audio/"):
            raise ValueError("WhatsApp attachment is not an audio file")
        media_response = client.get(
            metadata["url"], headers=_whatsapp_headers()
        )
        media_response.raise_for_status()
        content = media_response.content
    if not content or len(content) > MAX_AUDIO_BYTES:
        raise ValueError("Audio file is empty or exceeds the 20 MB limit")
    return content, mime_type


def _transcription_file(content: bytes, mime_type: str) -> io.BytesIO:
    if "ogg" not in mime_type and "opus" not in mime_type:
        audio = io.BytesIO(content)
        if "webm" in mime_type:
            suffix = "webm"
        elif "mpeg" in mime_type or "mp3" in mime_type:
            suffix = "mp3"
        elif "wav" in mime_type:
            suffix = "wav"
        else:
            suffix = "m4a"
        audio.name = f"voice-note.{suffix}"
        return audio
    try:
        converted = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
             "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("ffmpeg is required to convert WhatsApp OGG/Opus audio") from error
    except subprocess.CalledProcessError as error:
        logger.warning("WhatsApp audio conversion failed: %s", error.stderr[:300].decode(errors="replace"))
        raise ValueError("Could not decode this WhatsApp audio format") from error
    audio = io.BytesIO(converted.stdout)
    audio.name = "voice-note.wav"
    return audio


def transcribe_voice(content: bytes, mime_type: str) -> str:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key is not configured")
    audio_file = _transcription_file(content, mime_type)
    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=60)
    result = client.audio.transcriptions.create(
        model=config.OPENAI_TRANSCRIPTION_MODEL,
        file=audio_file,
        prompt="Transcribe Hindi, Hinglish, or English exactly. Preserve spoken amounts and payment terms.",
    )
    transcript = result.text.strip()
    if not transcript:
        raise ValueError("No speech was recognized in the voice note")
    return transcript


def extract_expense(transcript: str) -> dict[str, Any]:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key is not configured")
    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=45)
    response = client.chat.completions.create(
        model=config.OPENAI_EXTRACTION_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract one user-reported expense from Hindi/Hinglish/English. "
                    "Return only JSON with amount_paise (integer or null), currency, "
                    "category, payment_method, merchant, description, transaction_type, "
                    "confidence (0..1), needs_confirmation (boolean). Convert rupees to paise. "
                    "Never infer an amount not spoken. Use needs_confirmation when amount or "
                    "expense intent is unclear. Allowed payment_method: cash, upi, card, bank, "
                    "unknown. Categories should be concise lower-case labels."
                ),
            },
            {"role": "user", "content": transcript},
        ],
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    if not isinstance(payload, dict):
        raise ValueError("Expense extraction returned an invalid JSON object")
    amount = payload.get("amount_paise")
    if amount is not None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
            amount = None
        else:
            payload["amount_paise"] = round(amount)
    try:
        confidence = float(payload.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    payment_method = payload.get("payment_method")
    payment_method_is_clear = payment_method in {"cash", "upi", "card", "bank"}
    payload["needs_confirmation"] = bool(
        payload.get("needs_confirmation")
        or amount is None
        or payload.get("transaction_type") != "expense"
        or confidence < 0.65
        or not payment_method_is_clear
    )
    payload["confidence"] = max(0.0, min(1.0, confidence))
    payload["payment_method"] = payment_method if payment_method_is_clear else "unknown"
    payload["category"] = str(payload.get("category") or "uncategorized").lower()[:40]
    payload["currency"] = str(payload.get("currency") or "INR").upper()
    if payload["currency"] != "INR":
        payload["needs_confirmation"] = True
    payload["description"] = str(payload.get("description") or transcript)[:240]
    payload["transaction_type"] = "expense"
    return payload


def process_whatsapp_voice(message: dict[str, Any], sender: str) -> None:
    message_id = message["id"]
    try:
        audio_info = message.get("audio") or message.get("voice")
        if not audio_info or not audio_info.get("id"):
            raise ValueError("Message has no supported voice attachment")
        audio, mime_type = _download_whatsapp_audio(audio_info["id"])
        transcript = transcribe_voice(audio, mime_type)
        extracted = extract_expense(transcript)
        result_text = f"Maine suna: “{transcript}”\n"
        if extracted["needs_confirmation"]:
            result_text += "Amount ya expense detail clear nahi hai, isliye ise save nahi kiya. Kripya dobara amount aur payment method bolkar bhejein."
            update_inbound_message(message_id, "needs_confirmation")
            send_whatsapp_text(sender, result_text)
            return
        transaction = {
            **extracted,
            "source": "whatsapp_voice",
            "source_ref": message_id,
            "transcript": transcript,
        }
        try:
            sent_at = int(message.get("timestamp", ""))
            transaction["occurred_at"] = datetime.fromtimestamp(
                sent_at, timezone.utc
            ).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
        transaction_id, created = insert_transaction(transaction)
        stored = get_transaction(transaction_id)
        if stored and stored["status"] == "possible_duplicate":
            result_text += (
                f"₹{extracted['amount_paise'] / 100:,.2f} ka record possible duplicate "
                f"ke roop mein save hua; totals mein tab tak nahi jodega jab tak review na ho. "
                f"Record #{transaction_id}."
            )
        else:
            saved = "save ho gaya" if created else "pehle se record hai"
            result_text += (
                f"₹{extracted['amount_paise'] / 100:,.2f} {extracted['category']} expense "
                f"({extracted['payment_method']}) {saved}. Record #{transaction_id}."
            )
        if extracted.get("merchant"):
            result_text += f" Merchant: {extracted['merchant']}."
        if not created:
            update_inbound_message(message_id, "duplicate_delivery")
        else:
            update_inbound_message(message_id, "processed")
        send_whatsapp_text(sender, result_text)
    except Exception as error:
        code = type(error).__name__
        logger.error("WhatsApp voice processing failed: %s", code)
        update_inbound_message(message_id, "failed", code)
        try:
            send_whatsapp_text(
                sender,
                "Voice note process nahi ho paya. Kripya thodi der baad dobara bhejein.",
            )
        except Exception:
            logger.error("Could not send WhatsApp processing error reply")


def send_whatsapp_text(recipient: str, text: str) -> None:
    if not config.WHATSAPP_PHONE_NUMBER_ID:
        raise RuntimeError("WhatsApp phone number ID is not configured")
    url = (
        f"https://graph.facebook.com/{config.WHATSAPP_GRAPH_API_VERSION}/"
        f"{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    with httpx.Client(timeout=20) as client:
        response = client.post(
            url,
            headers={**_whatsapp_headers(), "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": text},
            },
        )
        response.raise_for_status()


def check_retell_authorization(authorization: str | None) -> bool:
    if not config.RETELL_FUNCTION_SECRET:
        return False
    return hmac.compare_digest(
        authorization or "",
        f"Bearer {config.RETELL_FUNCTION_SECRET}",
    )


def verify_retell_webhook(raw_body: bytes, signature: str | None) -> bool:
    if not config.RETELL_API_KEY or not signature:
        return False
    parts = {}
    for part in signature.split(","):
        key, separator, value = part.partition("=")
        if separator:
            parts[key.strip()] = value.strip()
    timestamp = parts.get("v")
    digest = parts.get("d")
    if not timestamp or not digest or not timestamp.isdigit():
        return False
    try:
        sent_at = int(timestamp)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    except (ValueError, OverflowError):
        return False
    if abs(now_ms - sent_at) > 5 * 60 * 1000:
        return False
    expected = hmac.new(
        config.RETELL_API_KEY.encode(),
        raw_body + timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, expected)


def is_authorized_phone_number(number: str | None) -> bool:
    if not number or not config.AUTHORIZED_PHONE_NUMBERS:
        return False
    normalized = "".join(character for character in number if character.isdigit())
    return normalized in config.AUTHORIZED_PHONE_NUMBERS
