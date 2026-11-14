from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from services.cohere_chat import CohereChat


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
