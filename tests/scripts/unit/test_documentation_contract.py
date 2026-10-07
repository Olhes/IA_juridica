"""Evita que la documentación activa vuelva a inventar versiones, rutas o enlaces."""

import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
GUIDES = [
    "README.md",
    "API_DOC.md",
    "DEPLOY_RENDER.md",
    "KNOWLEDGE_GRAPH_SETUP.md",
    "OAUTH_SETUP.md",
    "POSTGRES_CONNECTION_ISSUES.md",
    "backend/VALIDATION_GUIDE.md",
    "frontend/README_ARCHITECTURE.md",
]


def test_current_guides_identify_branch_date_and_existing_local_links():
    for name in GUIDES:
        path = ROOT / name
        content = path.read_text(encoding="utf-8")
        assert "v8" in content and "2026-10-06" in content, name
        for link in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", content):
            if "://" in link or link.startswith("#"):
                continue
            assert (path.parent / link.split("#")[0]).exists(), (name, link)


def test_documented_frontend_versions_and_root_commands_match_manifests():
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    root = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    guide = (ROOT / "frontend/README_ARCHITECTURE.md").read_text(encoding="utf-8")
    assert frontend["dependencies"]["next"] in guide
    assert frontend["dependencies"]["react"] in guide
    assert root["packageManager"].split("@")[1] in guide
    for name in GUIDES:
        content = (ROOT / name).read_text(encoding="utf-8")
        for command in re.findall(r"\bpnpm (?!-)([\w:-]+)", content):
            assert command in root["scripts"] or command == "install", (name, command)


def test_api_documented_explicit_routes_exist_in_current_source():
    routes = set()
    for name, prefix, receiver in [
        ("backend/main.py", "", "app"),
        ("backend/modules/chat/routes/chat_routes.py", "/chat", "router"),
    ]:
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == receiver
                    and decorator.func.attr in {"get", "post", "put", "delete"}
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    routes.add(
                        (decorator.func.attr.upper(), prefix + decorator.args[0].value)
                    )
    content = (ROOT / "API_DOC.md").read_text(encoding="utf-8")
    for method, path in re.findall(r"`(GET|POST|PUT|DELETE) (/[^`]+)`", content):
        assert (method, path) in routes, (method, path)
