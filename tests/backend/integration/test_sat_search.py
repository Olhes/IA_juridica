"""HTTP admin SAT sin lifespan ni llamadas externas."""

from tests.backend.fixtures.uploads import configured_client

HEADER = {"X-API-Key": "test-admin-key-with-enough-entropy"}
PLAN = {"query": "protección", "as_of": "2026-10-10"}


def test_search_and_history_require_admin_and_abstain_on_empty_corpus(
    monkeypatch, tmp_path
):
    client, _ = configured_client(monkeypatch, tmp_path)
    assert client.post("/sat-graph/search", json=PLAN).status_code == 403
    response = client.post("/sat-graph/search", json=PLAN, headers=HEADER)
    assert response.status_code == 200
    assert response.json()["state"] == "abstain"
    assert response.json()["api"]["requests"] == 0
    assert (
        client.get(
            "/sat-graph/history?resource_id=pe:ley:30364&component=art-1"
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/sat-graph/history?resource_id=pe:ley:30364&component=art-1",
            headers=HEADER,
        ).json()["state"]
        == "abstain"
    )


def test_search_rejects_ambiguous_date_and_unknown_fields(monkeypatch, tmp_path):
    client, _ = configured_client(monkeypatch, tmp_path)
    for overrides in ({"as_of": "2026"}, {"component": "art-1"}, {"relax_date": True}):
        assert (
            client.post(
                "/sat-graph/search", json={**PLAN, **overrides}, headers=HEADER
            ).status_code
            == 422
        )


def test_voyage_opt_in_without_credentials_returns_sanitized_503(monkeypatch, tmp_path):
    from config.settings import settings
    from pydantic import SecretStr

    client, _ = configured_client(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "VOYAGE_API_KEY", SecretStr(""))
    result = client.post("/sat-graph/search?use_voyage=true", json=PLAN, headers=HEADER)
    assert result.status_code == 503 and "VOYAGE_API_KEY" not in result.text
