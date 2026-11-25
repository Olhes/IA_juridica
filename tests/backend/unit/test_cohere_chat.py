from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from services.cohere_chat import CohereChat


def test_enriched_prompt_does_not_duplicate_complete_rag_evidence():
    from agents.pydantic_agents import LegalAgent
    from context.prompt_templates import format_legal_context

    text = 'EVIDENCIA COMPLETA ÚNICA CON LITERALES a), b) y c).'
    docs = [{'content': text, 'metadata': {'title': 'Fuente'}, 'relevance_score': 1}]
    enriched = format_legal_context('consulta', docs, include_documents=False)
    assert text not in enriched
    agent = object.__new__(LegalAgent)
    message = agent._build_user_prompt(enriched, {'answer': text, 'sources': ['Fuente']}, 'spanish')
    assert message.count(text) == 1


def test_sat_prompt_pairs_each_fragment_with_its_norm_and_article():
    from agents.pydantic_agents import LegalAgent
    from retrieval.sat_chat import _prompt_attribution

    hits = [
        {
            "resource_label": "Ley 27337 — Código de los Niños y Adolescentes",
            "label": "Artículo 96º.- Competencia.- Texto largo del encabezado",
        },
        {
            "resource_label": "Ley 31464 — procesos de alimentos",
            "label": "Artículo 164-A",
            "amending_heading": (
                "Artículo 3. Incorporación de los artículos 164-A y 167-A "
                "en el Código de los Niños y Adolescentes"
            ),
        },
    ]
    docs = [
        {
            "content": f"<!-- image --> Texto de prueba {i}.",
            "metadata": {
                "title": hit["resource_label"],
                "prompt_attribution": _prompt_attribution(hit),
            },
        }
        for i, hit in enumerate(hits, 1)
    ]
    agent = object.__new__(LegalAgent)
    prompt = agent._build_user_prompt(
        "consulta", {"method": "sat", "documents": docs, "answer": "Texto de prueba 1."},
        "spanish",
    )
    assert ("E1 — Ley 27337 — Código de los Niños y Adolescentes — Artículo 96\n"
            "Texto de prueba 1.") in prompt
    assert ("E2 — Código de los Niños y Adolescentes — Artículo 164-A · "
            "Incorporado por: Ley 31464 — procesos de alimentos\nTexto de prueba 2.") in prompt
    assert prompt.count("Texto de prueba 1.") == 1
    assert "Fuentes detectadas:" not in prompt
    assert "<!-- image -->" not in prompt


def test_sat_attribution_does_not_guess_which_code_an_ambiguous_heading_amends():
    from retrieval.sat_chat import _prompt_attribution

    assert _prompt_attribution({
        "resource_label": "Ley de prueba",
        "label": "Artículo 164-A",
        "amending_heading": "Modificación del Código Civil y del Código Procesal Civil",
    }) == {"norm": "Ley de prueba", "section": "Artículo 164-A"}


def test_shared_legal_prompt_keeps_grounding_and_safety_even_with_a_custom_role(monkeypatch):
    from context.prompt_templates import get_legal_system_prompt

    monkeypatch.setenv("SYSTEM_PROMPT", "Rol personalizado")
    prompt = get_legal_system_prompt()
    assert prompt.startswith("Rol personalizado\n\n")
    assert "norma y la sección del mismo bloque" in prompt
    assert "servicios\n  locales de emergencia" in prompt
    assert "sin añadir una traducción" in prompt
    for unsupported in ("25%", "agricultura", "no hay plazo", "10 watamanta", "proceso gratuito"):
        assert unsupported not in prompt.casefold()


async def test_cohere_chat_and_stream_send_the_same_system_prompt_once():
    from agents.pydantic_agents import LegalAgent
    from context.prompt_templates import get_legal_system_prompt

    def stream(**kwargs):
        stream_calls.append(kwargs)
        async def chunks():
            yield NS(text="Orientación en español.")

        return chunks()

    stream_calls = []
    agent = object.__new__(LegalAgent)
    agent.model_name = "test"
    agent.cohere_client = NS(
        chat=AsyncMock(return_value=NS(text="Orientación en español.")), chat_stream=stream,
    )
    await agent.respond_general("Consulta", {})
    assert [text async for text in agent.stream_general_text("Consulta", {})] == ["Orientación en español."]
    sent = agent.cohere_client.chat.await_args.kwargs
    assert sent["preamble"] == stream_calls[0]["preamble"] == get_legal_system_prompt()
    assert sent["message"] == stream_calls[0]["message"]
    assert "Idioma de redacción indicado: español" in sent["message"]
    assert "servicios" not in sent["message"]
    assert sent["message"].count("CONSULTA DEL USUARIO") == 1


def test_sat_pension_prompt_keeps_article_and_norm_without_injecting_unsupported_claims():
    from agents.pydantic_agents import LegalAgent
    from context.context_engineering import ContextEngineer

    question = ("El papá de mi hija dejó de pasarme dinero y no sé dónde trabaja. "
                "¿Puedo pedir una pensión de alimentos y qué necesito para hacerlo?")
    body = "No consignar el lugar de trabajo no impide la admisión de la demanda."
    doc = {"content": body, "metadata": {
        "title": "Ley 31464",
        "prompt_attribution": {
            "norm": "Código de los Niños y Adolescentes", "section": "Artículo 164-A",
            "relation": "Incorporado por",
        },
    }}
    enriched, context = ContextEngineer().build_legal_prompt(question, [doc], include_documents=False)
    prompt = object.__new__(LegalAgent)._build_user_prompt(
        enriched, {"method": "sat", "documents": [doc], "answer": body}, "spanish",
    )
    assert context["legal_topic"] == "pensión_alimentos"
    assert context["detected_location"] is None
    assert "Tema legal detectado: pensión_alimentos" in prompt
    assert question in prompt
    for unsupported in ("25%", "agricultura", "no hay plazo", "proceso gratuito"):
        assert unsupported not in prompt.casefold()
    assert ("E1 — Código de los Niños y Adolescentes — Artículo 164-A"
            " · Incorporado por: Ley 31464\n" + body) in prompt
    assert prompt.count(body) == 1


def test_topic_classifier_avoids_payment_only_and_recognizes_visits():
    from context.context_engineering import ContextEngineer

    classifier = ContextEngineer()
    assert classifier._detect_legal_type("desalojo por falta de pago del alquiler") == "general"
    assert classifier._detect_legal_type("¿cómo solicito el régimen de visitas de mis hijos?") == "regimen_visitas"
    assert classifier._detect_legal_type("solicito una pensión de alimentos") == "pensión_alimentos"


async def test_pension_fallback_leaves_unverified_amount_and_timeline_unspecified():
    from agents.pydantic_agents import LegalAgent

    result = await object.__new__(LegalAgent)._fallback_pension_response("Consulta", {})
    assert result.calculo_basico is None
    assert result.plazos == []


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


@pytest.mark.asyncio
async def test_reasoning_model_passes_explicit_thinking_option(monkeypatch):
    from agents.pydantic_agents import LegalAgent
    from config.settings import settings

    stream_calls = []

    def stream(**kwargs):
        stream_calls.append(kwargs)
        async def chunks():
            yield NS(text="Respuesta completa.")
        return chunks()

    agent = object.__new__(LegalAgent)
    agent.model_name = "command-a-plus-05-2026"
    agent.cohere_client = NS(
        chat=AsyncMock(return_value=NS(text="Respuesta completa.")),
        chat_stream=stream,
    )
    monkeypatch.setattr(settings, "COHERE_THINKING_ENABLED", False)
    monkeypatch.setattr(settings, "COHERE_THINKING_TOKEN_BUDGET", None)
    await agent.respond_general("Consulta", {})
    assert [t async for t in agent.stream_general_text("Consulta", {})] == ["Respuesta completa."]
    # command-a-plus leaks chain-of-thought into text blocks when sent type="disabled";
    # default disabled mode uses a minimal hidden containment budget so text stays clean.
    assert agent.cohere_client.chat.await_args.kwargs["thinking"] == {"type": "enabled", "token_budget": 64}
    assert stream_calls[0]["thinking"] == {"type": "enabled", "token_budget": 64}

    agent.model_name = "command-a-reasoning-08-2025"
    await agent.respond_general("Consulta", {})
    assert agent.cohere_client.chat.await_args.kwargs["thinking"] == {"type": "disabled"}

    agent.model_name = "command-a-plus-05-2026"
    monkeypatch.setattr(settings, "COHERE_THINKING_ENABLED", True)
    monkeypatch.setattr(settings, "COHERE_THINKING_TOKEN_BUDGET", 1024)
    await agent.respond_general("Consulta", {})
    assert agent.cohere_client.chat.await_args.kwargs["thinking"] == {"type": "enabled", "token_budget": 1024}

    agent.model_name = "command-r7b-12-2024"
    await agent.respond_general("Consulta", {})
    assert "thinking" not in agent.cohere_client.chat.await_args.kwargs


@pytest.mark.asyncio
async def test_cohere_chat_and_stream_log_warning_on_max_tokens(monkeypatch, caplog):
    import logging

    chat = AsyncMock(return_value=NS(
        finish_reason="MAX_TOKENS",
        message=NS(content=[NS(type="text", text="Texto cortado")]),
    ))

    async def stream(**kwargs):
        yield NS(type="content-delta", delta=NS(message=NS(content=NS(text="Texto cortado"))))
        yield NS(type="message-end", delta=NS(finish_reason="MAX_TOKENS", usage=None))

    monkeypatch.setattr("services.cohere_chat.cohere.AsyncClientV2", lambda **_: NS(chat=chat, chat_stream=stream))
    client = CohereChat("secret")
    with caplog.at_level(logging.WARNING, logger="ia_juridica.cohere"):
        resp = await client.chat(message="private", model="command-a-plus-05-2026")
        chunks = [e.text async for e in client.chat_stream(message="private", model="command-a-plus-05-2026")]
    assert resp.text == "Texto cortado"
    assert resp.finish_reason == "MAX_TOKENS"
    assert chunks == ["Texto cortado"]
    assert caplog.text.count("cohere_truncated_max_tokens") == 2
    assert "private" not in caplog.text and "secret" not in caplog.text
    assert chat.await_args.kwargs["thinking"] == {"type": "enabled", "token_budget": 64}

