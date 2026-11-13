"""Adaptador de SAT para el contrato de recuperación del chat."""
import asyncio
from datetime import date
from pathlib import Path

from ingestion.sat_graph.store import SATGraphStore
from retrieval.sat import SATRetriever, SearchPlan
from retrieval.sat_citations import references, requests_literals, resolve_reference, with_prior_reference


class SATChatRetriever:
    def __init__(self, graph_path: Path, as_of: str | None = None):
        self.graph_path = Path(graph_path)
        if not self.graph_path.is_file():
            raise FileNotFoundError(f"No existe el grafo SAT: {self.graph_path}")
        self.as_of = date.fromisoformat(as_of) if as_of else None

    def get_cache_revision(self):
        # La base puede cambiar entre la generación de la clave y la consulta.
        return None

    @property
    def documents(self):
        # El validador utiliza exactamente la evidencia del resultado SAT, no LightRAG.
        return {}

    def _search(self, query, top_k, candidates, prior_questions=()):
        graph = SATGraphStore(self.graph_path).export()
        current = query.partition("\nContexto de preguntas anteriores:\n")[0]
        parsed = with_prior_reference(references(current), prior_questions)
        q, resources, articles, incisos, numerals, ambiguous = parsed
        retriever = SATRetriever(graph)
        resolved = set()
        for identity in resources:
            if identity in retriever.nodes or identity.count("-") != 1 or ":ley:" in identity:
                resolved.add(identity)
                continue
            matches = {key for key, node in retriever.nodes.items()
                       if node["type"] == "Resource" and key.startswith(identity + "-")}
            # An abbreviated citation never picks one of several ministries by score.
            resolved.update(matches if len(matches) == 1 else {identity})
        lexical_query = query
        if prior_questions and not articles:
            lexical_query = query + "\nContexto de preguntas anteriores:\n" + "\n".join(prior_questions)[-3000:]
        plan = SearchPlan(query=lexical_query[:4000], as_of=self.as_of, top_k=min(top_k, 20),
                          candidates=min(max(top_k, candidates), 100),
                          resource_ids=sorted(resolved) if len(resolved) == 1 else [])
        if len(resources) == 1 and articles:
            return resolve_reference(retriever, plan, (q, resolved, articles, incisos, numerals, ambiguous))
        if requests_literals(q):
            return {
                "engine": "sat", "state": "abstain", "reason": "unresolved_reference",
                "candidate_count": 0, "eligible_chunks": 0, "hits": [],
                "warning": "Indica la norma y el artículo del que quieres los literales.",
                "reference": {"status": "unresolved"},
            }
        return retriever.search(plan)

    async def query_with_rerank(self, query, top_k=None, rerank_candidates=None, trace=None, *, prior_questions=()):
        result = await asyncio.to_thread(
            self._search, query, top_k or 5, rerank_candidates or 30, prior_questions
        )
        docs = [{
            'id': h['id'], 'document_id': h['work_id'], 'content': h['content'],
            'relevance_score': h['score'],
            'metadata': {'title': h['resource_label'], 'filename': h['resource_label'],
                         'retrieval_origin': 'sat', 'source_url': h['source_url'],
                         'version_id': h['version_id'], 'provenance_state': h['provenance_state'],
                         'citation': h.get('citation'),
                         'sat_section': h.get('sat_section'),
                         'snapshot_as_of': h.get('snapshot_as_of')},
        } for h in result['hits']]
        if trace is not None:
            trace.update(sat_result=result)
        warning = result['warning']
        if not result['eligible_chunks'] and not result.get('reference'):
            warning = ('No hay versiones SAT disponibles para la fecha consultada; el sistema se abstiene.'
                       if self.as_of else 'No hay versiones SAT disponibles en el grafo.')
        return {'answer': '\n\n'.join(d['content'] for d in docs) if docs else 'No hay evidencia suficiente en el corpus.',
                'documents': docs, 'sources': sorted({d['metadata']['title'] for d in docs}),
                'rerank_scores': [d['relevance_score'] for d in docs], 'method': 'sat',
                'total_candidates': result['candidate_count'], 'sat_warning': warning,
                'sat_reference': result.get('reference'), 'verbatim_answer': result.get('verbatim_answer'),
                'sat_as_of': self.as_of.isoformat() if self.as_of else None}
