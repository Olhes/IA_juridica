from collections import Counter

import pytest

from ingestion.sat_graph.official_cpc import CPC, CPC_PDF, CPC_URL, LAW, LAW_URL, parse_cpc
from retrieval.sat import SATRetriever, SearchPlan
from retrieval.sat_chat import SATChatRetriever
from scripts.publish_cpc_tuo import PDF_DIR, publish
from services.sat_corpus import CorpusEditor
from tests.backend.fixtures.sat_store import FixtureSATStore


def test_source_identity_is_pinned():
    with pytest.raises(ValueError, match="edición oficial cotejada"):
        parse_cpc((PDF_DIR / CPC_PDF).read_bytes() + b"\n")


@pytest.mark.slow
@pytest.mark.asyncio
async def test_full_official_cpc_and_amending_law_are_searchable(tmp_path):
    store = FixtureSATStore(tmp_path / "official.sqlite3")
    # Existing quotation from the previous law, including its parent article.
    with store._transaction() as db:
        for key, label, text in (("clause", "Artículo 564", "Redacción anterior de remuneración"),
                                 ("parent", "Artículo 4. Modificación del Código Procesal Civil",
                                  "Redacción anterior de remuneración")):
            store._node(db, f"work:{key}", "Work", {"resource_id": "pe:ley:31464", "component": key,
                                                    "label": label, "kind": "article"})
            store._node(db, f"ctv:{key}", "CTV", {"work_id": f"work:{key}", "scope": "PE",
                          "provenance_state": "user_attested_snapshot", "snapshot_as_of": "2022-05-04",
                          "valid_from": None, "valid_to": None, "checked_through": "2022-05-04", "review_id": "r"})
            store._node(db, f"clv:{key}", "CLV", {"language": "es", "text": text, "start": 0,
                          "source_url": "https://example.org", "evidence_id": "source"})
            store._edge(db, f"ctv:{key}", "has_text", f"clv:{key}", {})
        store._edge(db, "ctv:parent", "contains_version", "ctv:clause", {})

    publish(store, apply=True)
    editor = CorpusEditor(store)
    cpc = editor.get(CPC)
    inventory = Counter(n["kind"] for n in cpc["edition"]["components"])
    assert inventory["article"] == 872 and inventory["seccion"] == 6
    assert inventory["numeral"] > 400
    assert editor.get(LAW)["retrievable"] == 5
    graph = store.export()
    assert any(edge["type"] == "amended_by" and edge["target"] == LAW for edge in graph["edges"])
    assert not any(chunk["version_id"] in {"ctv:parent", "ctv:clause"}
                   for chunk in SATRetriever(graph).chunks(SearchPlan(query="ingresos")))

    rt = SATChatRetriever(store)
    for article, fragment in (("I", "tutela jurisdiccional"), ("424", "Requisitos de la demanda"),
                              ("471", "Artículos derogados"), ("564", "es inimpugnable"),
                              ("690-D", "Contradicción"), ("835", "derogado"),
                              ("847", "lectura fácil")):
        result = await rt.query_with_rerank(f"¿Qué dice el artículo {article} del CPC?")
        assert result["sat_reference"]["status"] == "exact"
        doc, = result["documents"]
        assert doc["metadata"]["source_url"] == CPC_URL
        assert fragment in " ".join(doc["content"].split())
        if article == "564":
            assert doc["metadata"]["prompt_attribution"]["modifier"].startswith("Ley 32006")

    part = await rt.query_with_rerank("¿Qué dice el numeral 5 del artículo 424 del CPC?")
    assert part["sat_reference"]["numeral"] == "5"
    assert part["documents"][0]["content"].startswith("5.")
    law = await rt.query_with_rerank("¿Qué dice el artículo único de la Ley 32006?")
    assert law["sat_reference"]["status"] == "exact"
    assert law["documents"][0]["metadata"]["source_url"] == LAW_URL
    assert "siete (7) días hábiles" in " ".join(law["documents"][0]["content"].split())
    repeal = await rt.query_with_rerank("¿Qué derogó la Ley 32006?")
    assert any("tercer párrafo" in doc["content"] for doc in repeal["documents"])
    old = await rt.query_with_rerank("¿Qué decía el artículo 564 en la Ley 31464?")
    assert old["sat_reference"]["status"] == "exact" and "texto sustituido" in old["sat_warning"]

    class WithHeadings:
        def chat_heading_snapshot(self):
            return graph

        def chat_article_snapshot(self, resource_id, work_id):
            return graph

        def chat_snapshot(self, resource_id=None):
            return graph

    selective = SATChatRetriever(WithHeadings())
    for question in ("¿Qué dice el artículo 564 según la Ley 32006?",
                     "¿Qué dice el artículo 564 del CPC modificado por la Ley 32006?"):
        match = await selective.query_with_rerank(question)
        assert match["sat_reference"]["resource_id"] == CPC
        assert match["sat_reference"]["citation"].endswith("modificado por Ley 32006")
