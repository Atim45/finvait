import hashlib
import hmac
import time

from fastapi.testclient import TestClient

from app import config, database, main
from app.integrations import verify_retell_webhook


def _retell_signature(body: bytes, timestamp: str, api_key: str) -> str:
    digest = hmac.new(
        api_key.encode(),
        body + timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"v={timestamp},d={digest}"


def test_audio_demo_transcribes_and_persists_without_meta(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "local-test-key")
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "audio.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    monkeypatch.setattr(main, "transcribe_voice", lambda audio, mime: "Aaj sabzi ke 250 rupaye cash diye")
    monkeypatch.setattr(
        main,
        "extract_expense",
        lambda transcript: {
            "amount_paise": 25000,
            "currency": "INR",
            "category": "groceries",
            "payment_method": "cash",
            "merchant": None,
            "description": "Vegetables",
            "transaction_type": "expense",
            "confidence": 0.95,
            "needs_confirmation": False,
        },
    )
    with TestClient(main.app) as client:
        response = client.post(
            "/api/demo/process-audio?mime_type=audio%2Fwebm",
            content=b"valid audio test fixture",
            headers={"Content-Type": "audio/webm"},
        )
        saved = client.get("/api/transactions")
    assert response.status_code == 200
    assert response.json()["transcript"] == "Aaj sabzi ke 250 rupaye cash diye"
    assert response.json()["status"] == "saved"
    assert saved.json()[0]["source"] == "demo_audio_upload"


def test_custom_voice_transcribes_locally_without_openai(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "LOCAL_WHISPER_MODEL", "base")
    monkeypatch.setattr(
        main,
        "transcribe_local_audio",
        lambda audio, mime: "Aaj 200 ki sabzi order kari hai",
    )
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "local-whisper.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/demo/transcribe-audio?mime_type=audio%2Fwebm",
            content=b"captured browser audio",
            headers={"Content-Type": "audio/webm"},
        )
        transactions = client.get("/api/transactions")
    assert response.status_code == 200
    assert response.json() == {
        "transcript": "Aaj 200 ki sabzi order kari hai",
        "engine": "faster-whisper",
        "model": "base",
    }
    assert transactions.json() == []


def test_local_whisper_endpoint_rejects_unsupported_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "unsupported.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/demo/transcribe-audio?mime_type=application%2Foctet-stream",
            content=b"not audio",
            headers={"Content-Type": "application/octet-stream"},
        )
    assert response.status_code == 415


def test_local_speech_endpoint_returns_playable_wav_without_openai(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(main, "synthesize_speech", lambda text: b"local-wav-audio")
    with TestClient(main.app) as client:
        response = client.post(
            "/api/demo/speech",
            json={"text": "You spent less this week. Nice work!"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"local-wav-audio"


def test_linked_local_speech_endpoint_returns_playable_wav(monkeypatch):
    monkeypatch.setattr(main, "synthesize_speech", lambda text: f"audio:{text}".encode())
    with TestClient(main.app) as client:
        response = client.get(
            "/api/demo/speech",
            params={"text": "You saved this week."},
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"audio:You saved this week."


def test_whatsapp_webhook_verification_uses_meta_query_names(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WHATSAPP_VERIFY_TOKEN", "local-test-token")
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    with TestClient(main.app) as client:
        response = client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "challenge-value",
                "hub.verify_token": "local-test-token",
            },
        )
    assert response.status_code == 200
    assert response.text == "challenge-value"


def test_retell_custom_function_accepts_standard_args_body(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RETELL_FUNCTION_SECRET", "local-function-secret")
    monkeypatch.setattr(config, "AUTHORIZED_PHONE_NUMBERS", {"919876543210"})
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "retell.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/retell/finance",
            headers={"Authorization": "Bearer local-function-secret"},
            json={
                "name": "get_finance_summary",
                "args": {"query": "Is mahine kharch?"},
                "call": {"call_id": "test-call", "from_number": "+919876543210"},
            },
        )
    assert response.status_code == 200
    assert "result" in response.json()
    assert response.json()["call_id"] == "test-call"


def test_retell_rejects_callers_outside_the_allowlist(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RETELL_FUNCTION_SECRET", "local-function-secret")
    monkeypatch.setattr(config, "AUTHORIZED_PHONE_NUMBERS", {"919876543210"})
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "unauthorized.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/retell/finance",
            headers={"Authorization": "Bearer local-function-secret"},
            json={
                "args": {"query": "How much did I spend?"},
                "call": {"from_number": "+919999999999"},
            },
        )
    assert response.status_code == 403


def test_retell_webhook_saves_inbound_recording_and_transcript(monkeypatch, tmp_path):
    api_key = "local-webhook-key"
    monkeypatch.setattr(config, "RETELL_API_KEY", api_key)
    monkeypatch.setattr(config, "AUTHORIZED_PHONE_NUMBERS", {"919876543210"})
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "recordings.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    now_ms = int(time.time() * 1000)
    body = (
        "{"
        '"event":"call_ended",'
        '"call":{'
        '"call_type":"phone_call",'
        '"direction":"inbound",'
        '"call_id":"retell-demo-call",'
        '"from_number":"+919876543210",'
        '"call_status":"ended",'
        '"start_timestamp":' + str(now_ms - 60000) + ","
        '"end_timestamp":' + str(now_ms) + ","
        '"duration_ms":60000,'
        '"transcript":"User: Is mahine kitna kharch hua?\\n",'
        '"recording_url":"https://retellai.s3.us-west-2.amazonaws.com/call/recording.wav"'
        "}}"
    ).encode()
    signature = _retell_signature(body, str(now_ms), api_key)
    with TestClient(main.app) as client:
        response = client.post(
            "/webhooks/retell",
            content=body,
            headers={"X-Retell-Signature": signature, "Content-Type": "application/json"},
        )
        retry = client.post(
            "/webhooks/retell",
            content=body,
            headers={"X-Retell-Signature": signature, "Content-Type": "application/json"},
        )
        calls = client.get("/api/calls")
    assert response.status_code == 200
    assert retry.status_code == 200
    assert response.json()["status"] == "processed"
    assert len(calls.json()) == 1
    assert calls.json()[0]["processing_status"] == "recording_and_transcript_ready"
    assert calls.json()[0]["recording_url"].endswith("/recording.wav")


def test_retell_webhook_signature_rejects_old_events_and_tampering(monkeypatch):
    monkeypatch.setattr(config, "RETELL_API_KEY", "local-webhook-key")
    body = b'{"event":"call_ended"}'
    old_timestamp = str(int(time.time() * 1000) - 6 * 60 * 1000)
    old_signature = _retell_signature(body, old_timestamp, "local-webhook-key")
    assert not verify_retell_webhook(body, old_signature)

    now = str(int(time.time() * 1000))
    valid_signature = _retell_signature(body, now, "local-webhook-key")
    assert verify_retell_webhook(body, valid_signature)
    assert not verify_retell_webhook(body + b" ", valid_signature)


def test_retell_web_call_can_query_finances_without_pstn_number(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RETELL_FUNCTION_SECRET", "local-function-secret")
    monkeypatch.setattr(config, "AUTHORIZED_PHONE_NUMBERS", set())
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "web-call-finance.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/retell/finance",
            headers={"Authorization": "Bearer local-function-secret"},
            json={
                "args": {"query": "How much did I spend this month?"},
                "call": {"call_type": "web_call", "call_id": "browser-call"},
            },
        )
    assert response.status_code == 200
    assert response.json()["call_id"] == "browser-call"


def test_cloudflare_tunnel_only_exposes_retell_endpoints(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "tunnel-guard.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    with TestClient(main.app) as client:
        health = client.get("/health", headers={"Cf-Connecting-Ip": "203.0.113.10"})
        transactions = client.get(
            "/api/transactions",
            headers={"Cf-Connecting-Ip": "203.0.113.10"},
        )
        calls = client.get("/api/calls", headers={"Cf-Connecting-Ip": "203.0.113.10"})
    assert health.status_code == 403
    assert transactions.status_code == 403
    assert calls.status_code == 403


def test_retell_web_call_recording_stored_without_phone_number(monkeypatch, tmp_path):
    api_key = "local-webhook-key"
    monkeypatch.setattr(config, "RETELL_API_KEY", api_key)
    monkeypatch.setattr(config, "AUTHORIZED_PHONE_NUMBERS", set())
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "web-call.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    now_ms = int(time.time() * 1000)
    body = (
        "{"
        '"event":"call_ended",'
        '"call":{'
        '"call_type":"web_call",'
        '"call_id":"browser-call",'
        '"call_status":"ended",'
        '"start_timestamp":' + str(now_ms - 30000) + ","
        '"end_timestamp":' + str(now_ms) + ","
        '"duration_ms":30000,'
        '"transcript":"User: Namaste\\nAgent: Namaste ji\\n",'
        '"recording_url":"https://retellai.s3.us-west-2.amazonaws.com/call/web-recording.wav"'
        "}}"
    ).encode()
    with TestClient(main.app) as client:
        response = client.post(
            "/webhooks/retell",
            content=body,
            headers={
                "X-Retell-Signature": _retell_signature(body, str(now_ms), api_key),
                "Content-Type": "application/json",
            },
        )
        calls = client.get("/api/calls")
    assert response.status_code == 200
    assert calls.json()[0]["caller_number"] == "Browser caller"
    assert calls.json()[0]["direction"] == "web"
    assert calls.json()[0]["recording_url"].endswith("web-recording.wav")
