import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.pydantic_agents import LegalAgent  # sin "backend."


# @pytest.mark.asyncio
# ┌─ POR QUÉ: pytest no puede ejecutar funciones `async def` por defecto.
# │  Sin esta anotación, pytest encuentra la función pero no la ejecuta
# │  correctamente porque no tiene un event loop para manejar el async.
# │
# ├─ CUÁNDO USARLA: siempre que el test sea `async def` y no tengas
# │  configurado `asyncio_mode = "auto"` en pyproject.toml.
# │
# └─ CÓMO EVITARLA: agrega `asyncio_mode = "auto"` en [tool.pytest.ini_options]
#    de pyproject.toml y nunca más necesitarás escribirla.
@pytest.mark.asyncio
async def test_legal_agent_violence_response():
    print("\nInicializando agente...")
    agent = LegalAgent()
    query = "Mi pareja me golpea y me amenaza, ¿qué puedo hacer?"
    context = {"answer": "", "sources": []}
    print("Enviando consulta...\n")

    response = await agent.respond_to_violence(query, context)

    print("✅ RESPUESTA:")
    print(response)
    print("\n📊 Como JSON:")
    print(response.model_dump_json(indent=2))

    assert response is not None
    assert response.nivel_urgencia is not None
    assert response.tipo_violencia is not None
    assert len(response.medidas_inmediatas) > 0