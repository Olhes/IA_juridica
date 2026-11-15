from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from services.cohere_chat import CohereChat


def test_enriched_prompt_does_not_duplicate_complete_rag_evidence():
    from agents.pydantic_agents import LegalAgent
    from context.prompt_templates import PromptManager, PromptType

    text = 'EVIDENCIA COMPLETA ÚNICA CON LITERALES a), b) y c).'
    docs = [{'content': text, 'metadata': {'title': 'Fuente'}, 'relevance_score': 1}]
    manager = PromptManager()
    enriched = manager.build_prompt_for_cohere(PromptType.GENERAL_LEGAL, 'consulta', docs,
                                               include_documents=False)
    assert text not in enriched
    agent = object.__new__(LegalAgent)
    message = agent._build_user_prompt(enriched, {'answer': text, 'sources': ['Fuente']}, 'spanish')
    assert message.count(text) == 1


def test_general_response_does_not_include_an_appended_quechua_translation():
    from agents.pydantic_agents import LegalAgent

    agent = object.__new__(LegalAgent)
    response = agent._build_general_response(
        "El numeral 7.2 enumera los deberes. Quechua: texto adicional.", "¿Qué dice el artículo?"
    )
    assert response.respuesta_espanol == "El numeral 7.2 enumera los deberes."


@pytest.mark.asyncio
async def test_v2_chat_separates_system_and_user_and_joins_text_blocks(monkeypatch):
    chat = AsyncMock(return_value=NS(message=NS(content=[
        NS(type="text", text="Primera "), NS(type="text", text="parte"),
    ])))
    monkeypatch.setattr("services.cohere_chat.cohere.AsyncClientV2", lambda **_: NS(chat=chat))
    response = await CohereChat("fake").chat(message="Consulta", preamble="Sistema", model="test")
    assert response.text == "Primera parte"
    chat.assert_awaited_once_with(model="test", messages=[
        {"role": "system", "content": "Sistema"}, {"role": "user", "content": "Consulta"},
    ])


@pytest.mark.asyncio
async def test_v2_stream_yields_only_content_delta(monkeypatch):
    async def stream(**kwargs):
        assert kwargs["messages"] == [{"role": "user", "content": "Pregunta"}]
        yield NS(type="message-start")
        yield NS(type="content-delta", delta=NS(message=NS(content=NS(text="Texto"))))
        yield NS(type="message-end")

    monkeypatch.setattr("services.cohere_chat.cohere.AsyncClientV2", lambda **_: NS(chat_stream=stream))
    assert [event.text async for event in CohereChat("fake").chat_stream(message="Pregunta")] == ["Texto"]


@pytest.mark.asyncio
async def test_stream_records_only_billed_token_counts(monkeypatch, caplog):
    import logging
    async def stream(**kwargs):
        yield NS(type='message-end', delta=NS(usage=NS(billed_units=NS(input_tokens=17, output_tokens=4))))
    monkeypatch.setattr('services.cohere_chat.cohere.AsyncClientV2', lambda **_: NS(chat_stream=stream))
    with caplog.at_level(logging.INFO, logger='ia_juridica.cohere'):
        assert [event async for event in CohereChat('secret').chat_stream(message='private question', model='test')] == []
    assert 'input_tokens=17 output_tokens=4' in caplog.text
    assert 'private question' not in caplog.text and 'secret' not in caplog.text


def test_usage_accepts_float_counts_from_the_cohere_sdk(caplog):
    import logging
    from cohere.types import Usage, UsageBilledUnits
    from services.cohere_chat import _record_usage

    with caplog.at_level(logging.INFO, logger='ia_juridica.cohere'):
        _record_usage(Usage(billed_units=UsageBilledUnits(input_tokens=17, output_tokens=4)), 'test')
    assert 'input_tokens=17.0 output_tokens=4.0' in caplog.text
