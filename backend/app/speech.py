"""Optional local speech. Existing local model paths only: never auto-download."""

import subprocess
import tempfile
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock

from .config import settings
from .providers import ProviderUnavailable, openai_client

speech_lock = Lock()


def synthesize(text):
    if settings.tts_provider == "openai":
        audio = openai_client().audio.speech.create(
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            input=text,
            response_format="mp3",
        )
        return audio.read(), "audio/mpeg"
    model = Path(settings.piper_model_path)
    if not model.is_file() or not Path(str(model) + ".json").is_file():
        raise ProviderUnavailable(
            "Piper no preparado: configura un modelo .onnx local y su .onnx.json."
        )
    try:
        with tempfile.TemporaryDirectory(prefix="mazmi-tts-") as folder:
            output = Path(folder) / "speech.wav"
            subprocess.run(
                [settings.piper_executable, "-m", str(model), "-f", str(output)],
                input=text.encode(),
                capture_output=True,
                check=True,
                timeout=90,
            )
            return output.read_bytes(), "audio/wav"
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderUnavailable(
            "No se pudo ejecutar Piper local. Comprueba instalación y modelo."
        ) from exc


@lru_cache(maxsize=1)
def whisper(path):
    from faster_whisper import WhisperModel

    return WhisperModel(path, device="cpu", compute_type="int8", local_files_only=True)


def transcribe(data):
    if not settings.stt_model_path or not Path(settings.stt_model_path).is_dir():
        raise ProviderUnavailable(
            "STT local no preparado: configura STT_MODEL_PATH con Faster-Whisper descargado previamente."
        )
    try:
        import av

        with av.open(BytesIO(data)) as container:
            seconds = 0
            for frame in container.decode(audio=0):
                seconds += frame.samples / frame.sample_rate
                if seconds > 65:
                    raise ProviderUnavailable("Audio demasiado largo: máximo 60 segundos.")
        with speech_lock:
            segments, _ = whisper(settings.stt_model_path).transcribe(
                BytesIO(data), vad_filter=True
            )
            return " ".join(segment.text.strip() for segment in segments)[:8000]
    except (ImportError, OSError, ValueError) as exc:
        raise ProviderUnavailable(
            "Faster-Whisper no disponible o audio no válido. Comprueba dependencias locales."
        ) from exc
