import logging
import tempfile
from pathlib import Path
from threading import Lock

from .config import LOCAL_WHISPER_MODEL

logger = logging.getLogger(__name__)
_model = None
_model_lock = Lock()
_supported_suffixes = {
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/m4a": ".m4a",
    "audio/mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".mp4",
    "audio/mpga": ".mpga",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/x-m4a": ".m4a",
    "audio/x-wav": ".wav",
}


class LocalWhisperUnavailable(RuntimeError):
    pass


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                LOCAL_WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )
        except Exception as error:
            logger.error("Could not load local Whisper model: %s", type(error).__name__)
            raise LocalWhisperUnavailable(
                "The local Whisper model could not be loaded. Check the backend dependencies and internet connection, then retry."
            ) from error
    return _model


def transcribe_local_audio(audio: bytes, mime_type: str) -> str:
    suffix = _supported_suffixes.get(mime_type)
    if suffix is None:
        raise ValueError("Unsupported audio format")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as audio_file:
        audio_file.write(audio)
        audio_path = Path(audio_file.name)
    try:
        segments, _ = _get_model().transcribe(
            str(audio_path),
            beam_size=5,
            vad_filter=True,
        )
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        audio_path.unlink(missing_ok=True)
    if not transcript:
        raise ValueError("No speech was recognized in the recording")
    return transcript
