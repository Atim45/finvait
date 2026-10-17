import io
import logging
import threading
import wave
from pathlib import Path

import httpx
import numpy as np

from .config import KOKORO_MODEL_DIR

logger = logging.getLogger(__name__)
MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.1/kokoro-v1.0.int8.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.1/voices-v1.0.bin"
)
_model = None
_model_lock = threading.RLock()


class LocalSpeechUnavailable(RuntimeError):
    pass


def _download_file(url: str, target: Path) -> None:
    if target.is_file() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    output.write(chunk)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise LocalSpeechUnavailable("The Kokoro model download was empty.")
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from kokoro_onnx import Kokoro

            model_path = KOKORO_MODEL_DIR / "kokoro-v1.0.int8.onnx"
            voices_path = KOKORO_MODEL_DIR / "voices-v1.0.bin"
            _download_file(MODEL_URL, model_path)
            _download_file(VOICES_URL, voices_path)
            _model = Kokoro(str(model_path), str(voices_path))
        except Exception as error:
            logger.error("Could not load local Kokoro TTS: %s", type(error).__name__)
            raise LocalSpeechUnavailable(
                "Local speech could not start. Check the Kokoro installation and internet connection for the first model download."
            ) from error
    return _model


def synthesize_speech(text: str) -> bytes:
    with _model_lock:
        try:
            audio, sample_rate = _get_model().create(
                text,
                voice="af_sarah",
                speed=0.96,
                lang="en-us",
            )
            samples = np.asarray(audio, dtype=np.float32)
            pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
            output = io.BytesIO()
            with wave.open(output, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm.tobytes())
            return output.getvalue()
        except LocalSpeechUnavailable:
            raise
        except Exception as error:
            logger.error("Kokoro speech generation failed: %s", type(error).__name__)
            raise LocalSpeechUnavailable(
                "Could not generate speech with the local Kokoro model."
            ) from error
