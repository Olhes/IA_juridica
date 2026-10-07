"""Google OAuth through real HTTP routes; provider and database stay offline."""

from datetime import datetime, timezone
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from modules.auth.routes import auth_routes
from modules.auth.services import security


@pytest.fixture
def google_oauth(monkeypatch):
    config = {
        "GOOGLE_CLIENT_ID": "synthetic-client",
        "GOOGLE_CLIENT_SECRET": "synthetic-client-secret",
        "GOOGLE_REDIRECT_URI": "http://testserver/auth/google/callback",
        "GOOGLE_FRONTEND_CALLBACK_URI": "https://frontend.example.invalid/auth/callback",
        "GOOGLE_AUTHORIZATION_URL": "https://google.example.invalid/authorize",
        "GOOGLE_TOKEN_URL": "https://google.example.invalid/token",
        "GOOGLE_USERINFO_URL": "https://google.example.invalid/userinfo",
    }
    for name, value in config.items():
        monkeypatch.setattr(auth_routes.settings, name, value)
    monkeypatch.setattr(
        security, "SECRET_KEY", "synthetic-access-key-not-for-production-123"
    )
    monkeypatch.setattr(
        security, "REFRESH_SECRET_KEY", "synthetic-refresh-key-not-for-production-456"
    )
    profile = {
        "email": "ana@example.invalid",
        "name": "Ana",
        "picture": "https://avatar.example.invalid/ana",
    }
    user = {
        "id": "user-1",
        "email": profile["email"],
        "username": "ana",
        "full_name": "Ana",
        "picture": profile["picture"],
        "role": "user",
        "is_active": True,
    }
    db = SimpleNamespace(
        initialize=AsyncMock(),
        get_user_by_email=AsyncMock(return_value=None),
        create_user=AsyncMock(return_value=user),
        update_user=AsyncMock(),
        get_user_by_id=AsyncMock(return_value=user),
        get_user_roles=AsyncMock(return_value=[{"name": "user"}]),
    )
    monkeypatch.setattr(auth_routes, "PostgreSQLAdapter", lambda: db)
    service = security.AuthService()
    service.create_access_token = Mock(wraps=service.create_access_token)
    service.create_refresh_token = Mock(wraps=service.create_refresh_token)
    monkeypatch.setattr(auth_routes, "SecurityService", lambda: service)
    provider = {
        "token_body": {"access_token": "synthetic-google-token"},
        "profile_body": profile,
        "token_status": 200,
        "profile_status": 200,
    }
    requests = []

    def handle(request):
        requests.append(request)
        if str(request.url) == config["GOOGLE_TOKEN_URL"]:
            stage = "token"
        elif str(request.url) == config["GOOGLE_USERINFO_URL"]:
            stage = "profile"
        else:
            raise AssertionError(f"Unexpected provider URL: {request.url}")
        if provider.get("failure_stage") == stage:
            raise httpx.TimeoutException("synthetic provider timeout", request=request)
        if provider.get("invalid_json_stage") == stage:
            return httpx.Response(200, content=b"not-json")
        return httpx.Response(
            provider[f"{stage}_status"], json=provider[f"{stage}_body"]
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        auth_routes.httpx,
        "AsyncClient",
        lambda: real_client(
            transport=httpx.MockTransport(handle),
            trust_env=False,
        ),
    )
    app = FastAPI()
    app.include_router(auth_routes.router)
    with TestClient(app, follow_redirects=False) as client:
        yield SimpleNamespace(
            client=client,
            db=db,
            user=user,
            profile=profile,
            provider=provider,
            requests=requests,
            config=config,
            service=service,
        )


def assert_no_session(oauth, response, status, detail):
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert not response.headers.get_list("set-cookie")
    oauth.service.create_access_token.assert_not_called()
    oauth.service.create_refresh_token.assert_not_called()


def test_google_login_redirect_contains_oauth_parameters(google_oauth):
    oauth = google_oauth
    response = oauth.client.get("/auth/google")
    assert response.status_code == 307
    target = urlsplit(response.headers["location"])
    assert (
        f"{target.scheme}://{target.netloc}{target.path}"
        == oauth.config["GOOGLE_AUTHORIZATION_URL"]
    )
    assert parse_qs(target.query) == {
        "client_id": [oauth.config["GOOGLE_CLIENT_ID"]],
        "redirect_uri": [oauth.config["GOOGLE_REDIRECT_URI"]],
        "scope": ["openid email profile"],
        "response_type": ["code"],
        "access_type": ["offline"],
        "prompt": ["consent"],
    }
    assert not oauth.requests
    oauth.db.initialize.assert_not_awaited()


def test_google_login_requires_client_id(google_oauth, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "GOOGLE_CLIENT_ID", "")
    response = google_oauth.client.get("/auth/google")
    assert response.status_code == 500
    assert "Google OAuth no está configurado" in response.json()["detail"]
    assert not google_oauth.requests


@pytest.mark.parametrize("existing", [False, True], ids=["new-user", "existing-user"])
def test_google_callback_exchanges_code_and_issues_real_jwts(google_oauth, existing):
    oauth = google_oauth
    if existing:
        oauth.db.get_user_by_email.return_value = oauth.user
    before = datetime.now(timezone.utc).timestamp()
    response = oauth.client.get("/auth/google/callback", params={"code": "code +/&"})
    after = datetime.now(timezone.utc).timestamp()
    assert response.status_code == 307
    assert response.headers["location"] == oauth.config["GOOGLE_FRONTEND_CALLBACK_URI"]
    assert [request.method for request in oauth.requests] == ["POST", "GET"]
    assert parse_qs(oauth.requests[0].content.decode()) == {
        "code": ["code +/&"],
        "client_id": [oauth.config["GOOGLE_CLIENT_ID"]],
        "client_secret": [oauth.config["GOOGLE_CLIENT_SECRET"]],
        "redirect_uri": [oauth.config["GOOGLE_REDIRECT_URI"]],
        "grant_type": ["authorization_code"],
    }
    assert oauth.requests[1].headers["Authorization"] == "Bearer synthetic-google-token"
    oauth.db.initialize.assert_awaited_once_with()
    oauth.db.get_user_by_email.assert_awaited_once_with(oauth.profile["email"])
    if existing:
        oauth.db.create_user.assert_not_awaited()
        oauth.db.update_user.assert_awaited_once_with(
            "user-1", {"full_name": "Ana", "picture": oauth.profile["picture"]}
        )
    else:
        values = oauth.db.create_user.await_args.kwargs
        assert {
            key: values[key]
            for key in ("email", "username", "full_name", "picture", "role")
        } == {
            "email": oauth.profile["email"],
            "username": "ana",
            "full_name": "Ana",
            "picture": oauth.profile["picture"],
            "role": "user",
        }
        oauth.db.update_user.assert_not_awaited()
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    assert set(cookies) == {"access_token", "refresh_token"}
    for name, kind, key, lifetime in (
        ("access_token", "access", security.SECRET_KEY, 900),
        ("refresh_token", "refresh", security.REFRESH_SECRET_KEY, 604800),
    ):
        cookie = cookies[name]
        assert cookie["httponly"]
        assert cookie["samesite"] == "lax"
        assert cookie["path"] == "/"
        assert int(cookie["max-age"]) == lifetime
        payload = jwt.decode(cookie.value, key, algorithms=["HS256"])
        assert payload["user_id"] == "user-1"
        assert payload["email"] == oauth.profile["email"]
        assert payload["type"] == kind
        assert before + lifetime - 1 <= payload["exp"] <= after + lifetime
    oauth.service.create_access_token.assert_called_once()
    oauth.service.create_refresh_token.assert_called_once()
    assert "synthetic-google-token" not in response.headers["location"]


@pytest.mark.parametrize("existing", [False, True])
def test_google_callback_handles_optional_profile_fields(google_oauth, existing):
    oauth = google_oauth
    oauth.provider["profile_body"] = {"email": oauth.profile["email"]}
    if existing:
        oauth.db.get_user_by_email.return_value = oauth.user
    assert oauth.client.get("/auth/google/callback?code=valid").status_code == 307
    if existing:
        oauth.db.update_user.assert_awaited_once_with(
            "user-1", {"full_name": "Ana", "picture": oauth.user["picture"]}
        )
    else:
        assert oauth.db.create_user.await_args.kwargs["full_name"] == ""
        assert oauth.db.create_user.await_args.kwargs["picture"] == ""


@pytest.mark.parametrize("setting", ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"])
def test_google_callback_requires_configuration(google_oauth, monkeypatch, setting):
    monkeypatch.setattr(auth_routes.settings, setting, "")
    response = google_oauth.client.get("/auth/google/callback?code=valid")
    assert_no_session(google_oauth, response, 500, "Google OAuth no está configurado")
    assert not google_oauth.requests


@pytest.mark.parametrize("query,status", [("", 422), ("?code=", 400)])
def test_google_callback_rejects_missing_or_empty_code(google_oauth, query, status):
    response = google_oauth.client.get("/auth/google/callback" + query)
    assert response.status_code == status
    assert not response.headers.get_list("set-cookie")
    assert not google_oauth.requests
    google_oauth.db.initialize.assert_not_awaited()


@pytest.mark.parametrize("stage", ["token", "profile"])
@pytest.mark.parametrize("failure", ["http", "timeout", "invalid-json"])
def test_google_callback_provider_failures_do_not_issue_session(
    google_oauth, stage, failure, caplog
):
    oauth = google_oauth
    if failure == "http":
        oauth.provider[f"{stage}_status"] = 401
        oauth.provider[f"{stage}_body"] = {"error": "synthetic-private-provider-detail"}
    elif failure == "timeout":
        oauth.provider["failure_stage"] = stage
    else:
        oauth.provider["invalid_json_stage"] = stage
    response = oauth.client.get("/auth/google/callback?code=valid")
    assert_no_session(oauth, response, 500, "OAuth callback failed")
    assert "synthetic-private-provider-detail" not in caplog.text
    assert "synthetic provider timeout" not in caplog.text
    assert "synthetic-client-secret" not in caplog.text
    assert all(
        record.exc_info is None
        for record in caplog.records
        if record.name == "ia_juridica.auth"
    )
    assert len(oauth.requests) == (1 if stage == "token" else 2)
    oauth.db.initialize.assert_not_awaited()


@pytest.mark.parametrize("stage,body", [("token", {}), ("profile", {"name": "Ana"})])
def test_google_callback_requires_provider_token_and_email(google_oauth, stage, body):
    google_oauth.provider[f"{stage}_body"] = body
    response = google_oauth.client.get("/auth/google/callback?code=valid")
    assert_no_session(google_oauth, response, 500, "OAuth callback failed")
    google_oauth.db.create_user.assert_not_awaited()
    google_oauth.db.update_user.assert_not_awaited()


@pytest.mark.parametrize(
    "operation", ["initialize", "get_user_by_email", "create_user", "update_user"]
)
def test_google_callback_database_failures_do_not_issue_session(
    google_oauth, operation
):
    oauth = google_oauth
    if operation == "update_user":
        oauth.db.get_user_by_email.return_value = oauth.user
    getattr(oauth.db, operation).side_effect = RuntimeError(
        "synthetic-private-database-detail"
    )
    response = oauth.client.get("/auth/google/callback?code=valid")
    assert_no_session(oauth, response, 500, "OAuth callback failed")
    if operation in {"initialize", "get_user_by_email"}:
        oauth.db.create_user.assert_not_awaited()
        oauth.db.update_user.assert_not_awaited()


def test_google_callback_preserves_explicit_http_exception(google_oauth):
    google_oauth.db.initialize.side_effect = HTTPException(503, "Database unavailable")
    response = google_oauth.client.get("/auth/google/callback?code=valid")
    assert_no_session(google_oauth, response, 503, "Database unavailable")


def test_google_callback_cannot_issue_session_without_created_user(google_oauth):
    google_oauth.db.create_user.return_value = None
    response = google_oauth.client.get("/auth/google/callback?code=valid")
    assert_no_session(google_oauth, response, 500, "OAuth callback failed")


def test_google_session_can_read_profile_and_logout(google_oauth):
    oauth = google_oauth
    assert oauth.client.get("/auth/google/callback?code=valid").status_code == 307
    response = oauth.client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {**oauth.user, "roles": ["user"]}
    oauth.db.get_user_by_id.assert_awaited_once_with("user-1")
    oauth.db.get_user_roles.assert_awaited_once_with("user-1")
    response = oauth.client.post("/auth/logout")
    assert response.status_code == 200
    assert len(response.headers.get_list("set-cookie")) == 2
    assert not oauth.client.cookies
    assert oauth.client.get("/auth/me").status_code == 401
    assert len(oauth.requests) == 2
