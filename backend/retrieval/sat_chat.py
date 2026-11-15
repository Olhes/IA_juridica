"""Adaptador de SAT para el contrato de recuperación del chat."""
import asyncio
from collections import OrderedDict
from hashlib import sha256
from datetime import date
from threading import RLock

from ingestion.sat_graph.store import SATGraphStore
from retrieval.sat import SATRetriever, SearchPlan, fingerprint
from retrieval.sat_citations import match_article_heading, references, requests_literals, resolve_reference, with_prior_reference


def _expand_ranked_component(result, retriever, plan):
    """Pack complete eligible CLVs in rank order, never silently truncate them.

    Ranking chunks locate evidence; they are not the units sent to the model.
    Prefer the best complete provision over lower-ranked or overlapping context.
    """
    hits = result.get('hits', [])
    if not hits:
        return result
    eligible = retriever.eligible(plan)
    by_version = {}
    for item in eligible:
        by_version.setdefault(item['version']['id'], []).append(item)

    def descendants(version):
        seen, pending = set(), [version]
        while pending:
            current = pending.pop()
            for child in retriever.outgoing.get((current, 'contains_version'), ()):
                if child in by_version and child not in seen:
                    seen.add(child)
                    pending.append(child)
        return seen

    packed, selected, used, omitted = [], [], 0, []
    for hit in hits:
        candidates = by_version.get(hit.get('version_id'), [])
        reason = None
        if len(candidates) != 1:
            reason = 'ambiguous_component_text'
        else:
            item = candidates[0]
            node = item['text']
            text, start = node['text'], node['start']
            children = descendants(item['version']['id'])
            coherent = hit['content'] in text
            for child_id in children:
                for child in by_version[child_id]:
                    offset = child['text']['start'] - start
                    body = child['text']['text']
                    coherent = coherent and (
                        child['work']['resource_id'] == item['work']['resource_id']
                        and offset >= 0 and text[offset:offset + len(body)] == body)
            if not coherent:
                reason = 'inconsistent_component_structure'
            elif any(item['work']['resource_id'] == previous['work']['resource_id'] and (
                item['version']['id'] == previous['version']['id']
                or item['version']['id'] in covered
                or previous['version']['id'] in children
            ) for previous, covered in selected):
                omitted.append({'version_id': hit['version_id'], 'reason': 'structural_overlap'})
                continue
            elif used + len(text.encode('utf-8')) > plan.context_bytes:
                reason = 'complete_component_exceeds_budget'
        if reason:
            omitted.append({'version_id': hit['version_id'], 'reason': reason})
            if not packed:
                return {**result, 'hits': [], 'state': 'abstain', 'reason': reason,
                        'context_bytes': 0, 'omitted_components': omitted,
                        'reference': {'status': 'unresolved', 'reason': reason},
                        'warning': 'No puedo entregar íntegra la sección principal dentro del contexto disponible o con su estructura actual. Precisa un numeral o literal; no presentaré un fragmento como respuesta completa.'}
            continue
        size = len(text.encode('utf-8'))
        packed.append({**hit, 'content': text, 'start': start, 'end': start + len(text),
                       'text_sha256': sha256(text.encode('utf-8')).hexdigest(),
                       'id': 'tu:' + fingerprint([hit['version_id'], node['id'], 0, len(text)]),
                       'context_complete': True})
        selected.append((item, children))
        used += size
    return {**result, 'hits': packed, 'context_bytes': used, 'omitted_components': omitted}


class SATChatRetriever:
    def __init__(self, store: SATGraphStore, as_of: str | None = None):
        self.store = store
        self.as_of = date.fromisoformat(as_of) if as_of else None
        self._retrievers = OrderedDict()
        self._retrievers_lock = RLock()

    def _retriever_for(self, snapshot):
        """Reuse only the exact immutable snapshot returned by the store."""
        key = id(snapshot)
        with self._retrievers_lock:
            entry = self._retrievers.get(key)
            if entry is not None and entry[0] is snapshot:
                self._retrievers.move_to_end(key)
                return entry[1]
            retriever = SATRetriever(snapshot)
            self._retrievers[key] = (snapshot, retriever)
            self._retrievers.move_to_end(key)
            while len(self._retrievers) > 2:
                self._retrievers.popitem(last=False)
            return retriever

    def get_cache_revision(self):
        # La base puede cambiar entre la generación de la clave y la consulta.
        return None

    def corpus_ready(self) -> bool:
        """Sonda de disponibilidad del corpus para arranque y recuperación en caliente.

        Un store sin la capacidad (fixtures, SQLite) se considera listo: solo el
        adaptador PostgreSQL tiene un corpus ausente que pueda aparecer después.
        """
        checker = getattr(self.store, "is_ready", None)
        return bool(checker()) if callable(checker) else True

    @property
    def documents(self):
        # El validador utiliza exactamente la evidencia del resultado SAT, no LightRAG.
        return {}

    def _search(self, query, top_k, candidates, prior_questions=()):
        current = query.partition("\nContexto de preguntas anteriores:\n")[0]
        parsed = with_prior_reference(references(current), prior_questions)
        q, resources, articles, incisos, numerals, ambiguous = parsed
        snapshot = getattr(self.store, 'chat_snapshot', None)
        # Only an unambiguous, fully specified statute can be scoped before
        # loading the graph; abbreviated decrees require global resolution.
        selected = next(iter(resources)) if len(resources) == 1 and ':ley:' in next(iter(resources)) else None
        headings = getattr(self.store, 'chat_heading_snapshot', None)
        article_loader = getattr(self.store, 'chat_article_snapshot', None)
        header_retriever = None
        number = articles[0][1] if selected and len(articles) == 1 and not ambiguous else None
        if callable(headings) and ((not resources and not articles and not ambiguous and not prior_questions)
                                   or (selected and number and callable(article_loader))):
            header_graph = headings()
            header_retriever = self._retriever_for(header_graph)
            header_plan = SearchPlan(query=current[:4000], as_of=self.as_of)
            if not selected:
                matched = match_article_heading(header_retriever, header_plan, current)
                if matched:
                    selected, number = matched
        work_ids = set()
        if selected and number and header_retriever and callable(article_loader):
            scope = header_plan.model_copy(update={'resource_ids': [selected]})
            for item in header_retriever.eligible(scope):
                matches = references(item['work']['label'])[2]
                if len(matches) == 1 and matches[0][1] == number:
                    work_ids.add(item['work']['id'])
        if len(work_ids) == 1:
            graph = article_loader(selected, next(iter(work_ids)))
            # The corpus can change between heading selection and hydration.
            # In that case re-resolve against a single fresh global snapshot.
            if graph.get('chat_revision') != header_graph.get('chat_revision'):
                graph = snapshot() if callable(snapshot) else self.store.export()
        else:
            graph = snapshot(selected) if callable(snapshot) else self.store.export()
        retriever = self._retriever_for(graph)
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
                          structural_units=True,
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
        if not articles and not ambiguous and len(resources) <= 1:
            heading = match_article_heading(retriever, plan, current)
            if heading:
                resource, article = heading
                exact = plan.model_copy(update={"resource_ids": [resource]})
                citation = references(f"artículo {article}")[2]
                return resolve_reference(
                    retriever, exact, (q, {resource}, citation, incisos, numerals, False),
                    heading_list=True,
                )
        result = retriever.search(plan)
        if not result['hits'] and result['candidate_count']:
            result.update(reference={'status': 'unresolved'},
                          warning='La sección principal supera el presupuesto de contexto. Precisa un numeral o literal para consultar su texto completo.')
        return _expand_ranked_component(result, retriever, plan)

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
                         # Etiqueta estructural del work (p. ej. "Artículo 3"): permite
                         # agrupar los fragmentos recuperados por norma y artículo.
                         'section_label': h.get('label'),
                         'sat_section': h.get('sat_section'),
                         'context_complete': h.get('context_complete'),
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
                'sat_context_bytes': result.get('context_bytes'),
                'sat_omitted_components': result.get('omitted_components', []),
                'sat_as_of': self.as_of.isoformat() if self.as_of else None}
