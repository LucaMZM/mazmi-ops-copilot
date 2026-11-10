from pathlib import Path

import pytest

from app import speech
from app.config import settings
from app.providers import ProviderUnavailable


def test_local_voice_missing_assets_report_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "piper_model_path", "")
    monkeypatch.setattr(settings, "stt_model_path", "")
    with pytest.raises(ProviderUnavailable, match="Piper"):
        speech.synthesize("test")
    with pytest.raises(ProviderUnavailable, match="STT local"):
        speech.transcribe(b"not audio")


def test_piper_uses_local_files_and_no_shell(monkeypatch, tmp_path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"fake")
    Path(str(model) + ".json").write_text("{}")
    monkeypatch.setattr(settings, "piper_model_path", str(model))

    def run(args, **kwargs):
        assert args[1:3] == ["-m", str(model)] and "shell" not in kwargs
        assert kwargs["input"] == b"hello" and kwargs["timeout"] == 90
        Path(args[4]).write_bytes(b"RIFF-test-wave")

    monkeypatch.setattr(speech.subprocess, "run", run)
    assert speech.synthesize("hello") == (b"RIFF-test-wave", "audio/wav")
