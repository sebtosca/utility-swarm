from pathlib import Path

from cjs.observability.logging import get_logger

logger = get_logger(__name__)


def transcribe(audio_path: Path) -> str:
    """Transcribe audio to text using local Whisper. Returns empty string if Whisper is not installed."""
    try:
        import whisper
    except ImportError:
        logger.warning("whisper_not_installed", audio_path=str(audio_path))
        return ""

    try:
        model = whisper.load_model("base")
        result = model.transcribe(str(audio_path))
        text: str = result["text"]
        return text.strip()
    except Exception as exc:
        logger.warning("whisper_transcription_failed", audio_path=str(audio_path), error=str(exc))
        return ""
