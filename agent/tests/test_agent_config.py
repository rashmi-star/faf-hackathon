import pytest

import agent


def test_build_llm_uses_fal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    director_llm = agent.build_llm()

    assert director_llm.model == agent.FAL_LLM_MODEL
    assert director_llm.provider == "fal.run"


def test_build_llm_requires_fal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)

    with pytest.raises(RuntimeError, match="FAL_KEY is required"):
        agent.build_llm()


def test_elevenlabs_stt_uses_fast_server_vad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "STT_BACKEND", "elevenlabs")

    director_stt = agent.build_stt()

    assert director_stt._opts.language_code == "en"
    assert director_stt._opts.server_vad["min_silence_duration_ms"] == 500
