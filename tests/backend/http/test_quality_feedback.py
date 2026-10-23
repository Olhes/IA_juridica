"""POST /feedback, cola de candidatos, métricas publicadas y panel de administración (sin proveedores)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import main
from services import quality_access
from services.feedback_store import FeedbackIn, FeedbackStore

ADMIN = {"X-API-Key": "offline-admin-key"}
REQUEST_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def store(api, tmp_path, monkeypatch):
    instance = FeedbackStore(tmp_path / "feedback")
    monkeypatch.setattr(main.app.state, "feedback_store", instance, raising=False)
    return instance


def vote(**overrides):
    return {"request_id": REQUEST_ID, "rating": "down", "reason": "incorrecta", "language": "spanish", **overrides}


def conversation(monkeypatch, messages):
    chat = SimpleNamespace(
        get_conversation=AsyncMock(return_value=object()),
        get_conversation_messages=AsyncMock(return_value=messages),
    )
    monkeypatch.setattr(main, "chat_service", chat)
    return chat


def exchange(query="¿Cuánto es la pensión?", answer="Respuesta del asistente"):
    return [SimpleNamespace(role="user", content=query), SimpleNamespace(role="assistant", content=answer)]


def test_feedback_requires_an_anonymous_session(api, store):
    client, _, _ = api
    assert client.post("/feedback", json=vote()).status_code == 401


def test_a_thumbs_up_stores_only_labels_and_numbers(api, store):
    client, _, _ = api
    client.post("/session/bootstrap")
    response = client.post("/feedback", json={"request_id": REQUEST_ID, "rating": "up", "language": "quechua", "translation_quality": "alta"})
    assert response.status_code == 201 and response.json()["queued"] is False
    (item,) = store._items
    assert item["rating"] == "up" and item["translation_quality"] == "alta" and "query" not in item and "answer" not in item
    assert item["owner"] != "" and "principal" not in json.dumps(item)


def test_text_is_stored_only_when_the_person_shares_it_with_a_thumbs_down(api, store, monkeypatch):
    client, _, _ = api
    chat = conversation(monkeypatch, exchange())
    client.post("/session/bootstrap")
    private = client.post("/feedback", json=vote(conversation_id="c1"))  # sin share_text
    assert private.json()["queued"] is False and "query" not in store._items[-1]
    shared = client.post("/feedback", json=vote(request_id="f" * 32, conversation_id="c1", share_text=True, comment="falta el artículo"))
    assert shared.status_code == 201 and shared.json()["queued"] is True
    (candidate,) = store.queue("pending")
    assert candidate["query"] == "¿Cuánto es la pensión?" and candidate["answer"] == "Respuesta del asistente" and candidate["comment"] == "falta el artículo"
    assert chat.get_conversation.await_args.args[1] != ""  # se verifica el propietario antes de leer el texto
    client.post("/feedback", json={"request_id": "e" * 32, "rating": "up", "conversation_id": "c1", "share_text": True})
    assert all("query" not in i for i in store._items if i["rating"] == "up")


def test_a_foreign_or_unreadable_conversation_never_leaks_text(api, store, monkeypatch):
    client, _, _ = api
    client.post("/session/bootstrap")
    chat = conversation(monkeypatch, exchange())
    chat.get_conversation = AsyncMock(return_value=None)  # no es del propietario
    response = client.post("/feedback", json=vote(conversation_id="ajena", share_text=True))
    assert response.status_code == 201 and response.json()["queued"] is False
    assert store._items[-1]["text_unavailable"] is True and "query" not in store._items[-1]


@pytest.mark.parametrize(
    "payload",
    [
        vote(reason=None),
        {"request_id": REQUEST_ID, "rating": "up", "reason": "incorrecta"},
        vote(reason="inventado"),
        vote(comment="x" * 501),
        vote(request_id="no-es-hex"),
        vote(query="texto de la consulta"),
        vote(rating="meh"),
    ],
)
def test_invalid_feedback_is_rejected(api, store, payload):
    client, _, _ = api
    client.post("/session/bootstrap")
    assert client.post("/feedback", json=payload).status_code == 422 and store._items == []


def test_one_vote_per_person_and_request_the_latest_wins(api, store):
    client, _, _ = api
    client.post("/session/bootstrap")
    client.post("/feedback", json=vote())
    client.post("/feedback", json={"request_id": REQUEST_ID, "rating": "up"})
    assert [i["rating"] for i in store._items] == ["up"]


def test_the_queue_requires_admin_and_decisions_never_touch_the_gold(api, store, monkeypatch):
    client, _, _ = api
    conversation(monkeypatch, exchange())
    client.post("/session/bootstrap")
    queued = client.post("/feedback", json=vote(conversation_id="c1", share_text=True)).json()["id"]
    assert client.get("/feedback/queue").status_code == 403
    listing = client.get("/feedback/queue", headers=ADMIN).json()
    assert listing["summary"]["queue"]["pending"] == 1 and listing["items"][0]["id"] == queued
    assert client.post(f"/feedback/queue/{queued}/decision", json={"decision": "accept"}).status_code == 403
    assert client.post(f"/feedback/queue/{queued}/decision", json={"decision": "quizás"}, headers=ADMIN).status_code == 422
    assert client.post("/feedback/queue/no-existe/decision", json={"decision": "accept"}, headers=ADMIN).status_code == 404
    decided = client.post(f"/feedback/queue/{queued}/decision", json={"decision": "accept"}, headers=ADMIN)
    assert decided.json()["queue_status"] == "accepted"
    (skeleton,) = store.export_candidates()
    assert skeleton["status"] == "candidate" and skeleton["reviewers"] == [] and "required_facts" not in skeleton
    assert client.post(f"/feedback/queue/{queued}/decision", json={"decision": "reject"}, headers=ADMIN).status_code == 404


def test_the_store_survives_a_restart_and_summarises_reasons(tmp_path):
    first = FeedbackStore(tmp_path)
    first.add("persona-1", FeedbackIn(**vote(share_text=True)), query="q", answer="a")
    first.add("persona-2", FeedbackIn(**vote(reason="sin_fuentes", request_id="a" * 32)))
    first.add("persona-3", FeedbackIn(request_id="b" * 32, rating="up"))
    second = FeedbackStore(tmp_path)
    summary = second.summary()
    assert summary["total"] == 3 and summary["up"] == 1 and summary["down"] == 2
    assert summary["reasons"] == {"incorrecta": 1, "sin_fuentes": 1} and summary["queue"] == {"pending": 1, "accepted": 0, "rejected": 0}
    assert not list(tmp_path.glob("*.tmp"))


def test_published_metrics_are_public_and_default_to_unpublished(api, tmp_path, monkeypatch):
    client, _, _ = api
    path = tmp_path / "published.json"
    monkeypatch.setattr("services.quality_reports.PUBLISHED_PATH", path)
    monkeypatch.setattr(main, "load_published", lambda: __import__("services.quality_reports", fromlist=["x"]).load_published(path))
    assert client.get("/quality/published").json()["published"]["status"] == "sin_publicar"
    path.write_text(json.dumps({"schema": 1, "status": "preliminar", "suites": {"retrieval": {"measured": True}}, "notices": ["x"]}), encoding="utf-8")
    assert client.get("/quality/published").json()["published"]["suites"]["retrieval"]["measured"] is True


def test_admin_overview_gathers_comparison_gold_queue_and_stream_without_secrets(api, store, tmp_path, monkeypatch):
    client, _, _ = api
    compare_dir = tmp_path / "compare" / "aaa..bbb"
    compare_dir.mkdir(parents=True)
    (compare_dir / "report.json").write_text(json.dumps({
        "base": {"ref": "v8", "sha": "a" * 40}, "head": {"ref": "HEAD", "sha": "b" * 40}, "comparable": True, "missing": [],
        "verdict": {"verdict": "EMPEORÓ", "blocking": True, "blocks": [{"suite": "legal_qa", "kind": "afirmación_nueva_sin_respaldo", "case_id": "c1", "stratum": "limite", "detail": ["secreto"]}]},
        "suites": [{"suite": "legal_qa", "metrics": [{"metric": "legal_factuality", "scope": "macro", "base": 0.8, "head": 0.6, "delta": -0.2, "ci": [-0.3, -0.1], "status": "worse"}]}],
    }), encoding="utf-8")
    monkeypatch.setattr("services.quality_reports.RESULTS_DIR", tmp_path)
    monkeypatch.setattr(main, "admin_overview", lambda s, m: __import__("services.quality_reports", fromlist=["x"]).admin_overview(s, m, tmp_path))
    conversation(monkeypatch, exchange())
    client.post("/session/bootstrap")
    client.post("/feedback", json=vote(conversation_id="c1", share_text=True))
    assert client.get("/quality/admin/overview").status_code == 403
    overview = client.get("/quality/admin/overview", headers=ADMIN).json()["overview"]
    assert overview["comparison"]["verdict"] == "EMPEORÓ" and overview["comparison"]["blocking"] is True
    assert overview["comparison"]["blocks"][0] == {"suite": "legal_qa", "kind": "afirmación_nueva_sin_respaldo", "case_id": "c1", "stratum": "limite"}
    assert overview["gold"]["available"] is True and overview["gold"]["pending_lawyers"] >= 30 and overview["gold"]["pending_native_speakers"] >= 250
    assert overview["feedback"]["queue"]["pending"] == 1 and overview["feedback_queue"][0]["query"] == "¿Cuánto es la pensión?"
    assert "n" in overview["stream"] and "offline-admin-key" not in json.dumps(overview)


async def test_an_admin_user_without_the_api_key_is_accepted_and_others_are_not(monkeypatch):
    request = SimpleNamespace(cookies={"access_token": "token"})
    monkeypatch.setattr(quality_access, "roles_from_session", AsyncMock(return_value=["user", "admin"]))
    assert await quality_access.require_quality_admin(request, None) == "role"
    monkeypatch.setattr(quality_access, "roles_from_session", AsyncMock(return_value=["user"]))
    with pytest.raises(Exception) as denied:
        await quality_access.require_quality_admin(request, None)
    assert denied.value.status_code == 403
    monkeypatch.setattr(quality_access, "roles_from_session", AsyncMock(side_effect=RuntimeError("base de datos caída")))
    with pytest.raises(Exception) as failed:
        await quality_access.require_quality_admin(request, None)
    assert failed.value.status_code == 403  # un fallo nunca concede acceso
    monkeypatch.setattr(quality_access, "roles_from_session", AsyncMock(return_value=None))
    with pytest.raises(Exception):
        await quality_access.require_quality_admin(request, "clave-incorrecta")
