"""No se registra el texto de una persona cuando falla la síntesis."""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

from modules.voice.services.tts_service import TTSService


def test_importing_voice_service_does_not_import_torch_or_vits():
    backend = Path(__file__).resolve().parents[3] / "backend"
    subprocess.run(
        [sys.executable, "-c",
         "import sys; from modules.voice.services.tts_service import TTSService; "
         "assert 'torch' not in sys.modules; "
         "assert 'transformers.models.vits.modeling_vits' not in sys.modules"],
        env={**os.environ, "PYTHONPATH": str(backend)},
        check=True,
    )

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


def test_tts_speaks_visible_markdown_and_retains_written_ordinal_markers():
    service = object.__new__(TTSService)
    text = (
        "2. Lee [la **norma**](https://example.invalid/ley-(2026)).\n"
        "7. Artículo 164-A. <!-- NO LEER -->\n\n"
        "```js\nNO PRONUNCIAR\n```\n\nFinal"
    )
    assert service.normalize_text_for_tts(text, "es") == "2. Lee la norma. 7. Artículo 164-A. Final"


def test_tts_reads_quechua_legal_numbers_without_merging_digits():
    service = object.__new__(TTSService)
    assert service.normalize_text_for_tts("Ley 30364; artículo 10", "qu") == "Ley kimsa ch'usaq kimsa suqta tawa; artículo chunka"
