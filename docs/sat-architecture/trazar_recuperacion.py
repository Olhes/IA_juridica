"""Trazas de lectura para la documentación, sin Cohere ni datos de usuarios.

Desde raíz: uv run --no-sync python -B docs/sat-architecture/trazar_recuperacion.py
Requiere PostgreSQL local inicializado con el corpus publicado.
"""

from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

class ObservedReads:
    """Cuenta llamadas del recuperador; una llamada puede acertar en caché."""

    def __init__(self, store):
        self.store = store
        self.calls = []

    def __getattr__(self, name):
        operation = getattr(self.store, name)
        if name not in {"chat_heading_snapshot", "chat_article_snapshot", "chat_snapshot"}:
            return operation

        def observe(*args, **kwargs):
            graph = operation(*args, **kwargs)
            self.calls.append({
                "operation": name,
                "scope": args[0] if args else None,
                "nodes": len(graph["nodes"]),
                "edges": len(graph["edges"]),
            })
            return graph

        return observe


def main():
    from ingestion.sat_graph.runtime import runtime_sat_store
    from retrieval.sat_chat import SATChatRetriever

    store = ObservedReads(runtime_sat_store())
    # Runtime SAT with no explicit date, as used in the walkthrough.
    retriever = SATChatRetriever(store)
    cases = [
        ("encabezado", "¿Cuáles son las reglas para una audiencia única en un proceso de demanda de pensión de alimentos?", ()),
        ("literal", "En el artículo 8 de la Ley 30364, ¿cuáles son los cuatro supuestos del inciso d)?", ()),
        ("cotidiana", "El papá de mi hija dejó de pasarme dinero y no sé dónde trabaja. ¿Puedo pedir alimentos y qué necesito?", ()),
        ("sin_alcance", "Dame los literales.", ()),
    ]
    records = []
    for name, query, history in cases:
        store.calls.clear()
        output = retriever._search(query, top_k=5, candidates=30, prior_questions=history)
        hits = output["hits"]
        records.append({
            "case": name,
            "query": query,
            "reads": list(store.calls),
            "state": output["state"],
            "reason": output.get("reason"),
            "candidate_count": output["candidate_count"],
            "reference": output.get("reference"),
            "evidence_bytes": sum(len(h["content"].encode("utf-8")) for h in hits),
            "omissions": [x["reason"] for x in output.get("omitted_components", [])],
            "hits": [{
                "resource": h["resource_id"], "section": h.get("label") or
                (h.get("sat_section") or {}).get("path", [None])[-1],
                "version_id": h["version_id"], "citation": h.get("citation"),
                "path": (h.get("sat_section") or {}).get("path"),
                "start": h.get("start"), "end": h.get("end"),
                "sha256_observed": sha256(h["content"].encode("utf-8")).hexdigest(),
                "bytes": len(h["content"].encode("utf-8")),
            } for h in hits],
        })
    print(json.dumps(records, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
