"""No se registra el texto de una persona cuando falla la síntesis."""

import asyncio
import logging

from modules.voice.services.tts_service import TTSService


def test_tts_failure_does_not_log_private_input_or_exception(caplog):
    private_text = "información ficticia de una persona vulnerable"
    service = object.__new__(TTSService)
    service.mms_available = True

    def fail(*args, **kwargs):
        raise RuntimeError(private_text)

    service.mms_tokenizer = fail
    with caplog.at_level(logging.INFO, logger="ia_juridica.tts"):
        assert asyncio.run(service.synthesize_quechua(private_text)) is None
    assert private_text not in caplog.text
    assert "RuntimeError" in caplog.text
