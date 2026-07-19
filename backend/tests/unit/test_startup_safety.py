import builtins
import io
import sys

from modules.rag.services import lightrag_engine
from utils.console import configure_console_output


def test_disabled_neo4j_selects_networkx_without_importing_neo4j(monkeypatch):
    monkeypatch.setattr(lightrag_engine.settings, "NEO4J_ENABLED", False)
    original_import = builtins.__import__

    def reject_neo4j_import(name, *args, **kwargs):
        if name == "lightrag.kg.neo4j_impl":
            raise AssertionError("Neo4j storage must not load when disabled")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_neo4j_import)

    assert lightrag_engine._select_graph_storage() == "NetworkXStorage"


def test_console_output_replaces_unencodable_characters(monkeypatch):
    output = io.BytesIO()
    stream = io.TextIOWrapper(output, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)

    configure_console_output()
    print("Redis ready: \U0001f680")
    stream.flush()

    assert "\\U0001f680" in output.getvalue().decode("cp1252")
