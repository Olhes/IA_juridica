"""Resolve explicit references against eligible SAT versions, not BM25 scores."""
import re
from string import ascii_lowercase

from retrieval.sat import fingerprint, terms
from utils.text_match import fold

_N = r"(?:n\s*[.°ºo]*\s*)?"
_LAW = re.compile(rf"\bley\s+{_N}(\d{{4,6}})\b")
_DECREE = re.compile(
    rf"\b(decreto supremo|d\s*\.?\s*s\.?|resolucion ministerial|r\s*\.?\s*m\.?)\s*(?:-\s*)?"
    rf"{_N}(\d{{1,4}})\s*-\s*(\d{{4}})(?:\s*-\s*([a-z]+))?\b"
)
_ARTICLE = re.compile(r"\b(?:articulos?|arts?\.?)\s*(\d{1,4}(?:-[a-z])?)(?![a-z0-9])")
_ADDITIONAL = re.compile(r"^\s*[°º]?(?:\s*(?:,|y|e|a|al|[-–])\s*\d)")
_INCISO = re.compile(r"\b(?:inciso|literal|inc\.|lit\.)\s*\(?([a-zñ])\b")
_NUMERAL = re.compile(r"\b(?:numeral|num\.)\s*(\d+(?:\.\d+)*)\b")
_LABEL_MARK = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*)?\(?([a-zñ]|\d+(?:\.\d+)*)(?:[.)]|\s|$)")
_ENUMERATE = re.compile(
    r"\b(?:dame|dime|muestra(?:me)?|enumera(?:me)?|enumere|lista(?:me)?|liste|"
    r"transcribe|cuales son)\s+"
    r"(?:(?:los|todos|cada|cuatro|tres|dos|cinco|seis|\d+)\s+)*(supuestos|numerales|literales|incisos)\b"
)
_PART_MARK = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?\(?([a-zñ]|\d+)[.)][ \t]+", re.M)


def requests_literals(query):
    match = _ENUMERATE.search(query)
    return bool(match and match[1] in {"literales", "incisos"})


def match_article_heading(retriever, plan, query):
    """Match a full, distinctive heading in the current turn, not in history."""
    current = " " + " ".join(terms(query)) + " "
    matches = set()
    for item in retriever.eligible(plan):
        work = item["work"]
        if work.get("kind") != "article":
            continue
        label = fold(work["label"]).lstrip("# ")
        m = _ARTICLE.match(label)
        if not m:
            continue
        heading = terms(label[m.end():])
        minimum = 4
        if len(heading) < 4:
            # Some reviewed works label only the number, while the title is
            # preserved in the first line of the corresponding CLV.
            first_line = item['text']['text'].split('\n', 1)[0]
            full_label = fold(first_line).lstrip('# «“\" ')
            header = _ARTICLE.match(full_label)
            if header and header[1] == m[1]:
                candidate = terms(full_label[header.end():])
                if len([word for word in candidate if len(word) >= 3]) >= 2:
                    heading = candidate
                    minimum = 2
        if len(heading) >= minimum and " " + " ".join(heading) + " " in current:
            matches.add((len(heading), work["resource_id"], m[1]))
    if not matches:
        return None
    longest = max(length for length, _, _ in matches)
    best = {(resource, article) for length, resource, article in matches if length == longest}
    return next(iter(best)) if len(best) == 1 else None


def references(query):
    q = "".join("ñ" if char in "Ññ" else fold(char) for char in query)
    resources = {f"pe:ley:{m[1]}" for m in _LAW.finditer(q)}
    for m in _DECREE.finditer(q):
        kind = "ds" if m[1].startswith("d") else "rm"
        resources.add(f"pe:{kind}:{int(m[2]):03d}-{m[3]}" + (f"-{m[4]}" if m[4] else ""))
    articles = list(_ARTICLE.finditer(q))
    incisos = {m[1] for m in _INCISO.finditer(q)}
    numerals = {m[1] for m in _NUMERAL.finditer(q)}
    ambiguous = (
        len(articles) > 1 or any(_ADDITIONAL.match(q[m.end():]) for m in articles)
        or len(incisos) > 1 or len(numerals) > 1
        or bool(re.search(r"\b(?:incisos|literales)\s+\(?[a-z]\b[.)]?\s*(?:,|\b(?:y|e|al)\b)\s*\(?[a-z]\b", q))
    )
    return q, resources, articles, incisos, numerals, ambiguous


def with_prior_reference(parsed, prior_questions):
    """Only inherit a reference for a structural follow-up, never from model text."""
    q, resources, articles, incisos, numerals, ambiguous = parsed
    if resources or ambiguous or not (_ENUMERATE.search(q) or incisos or numerals):
        return parsed
    for previous in reversed(prior_questions):
        _, norms, prior_articles, prior_incisos, prior_numerals, prior_ambiguous = references(previous)
        if not norms and not prior_articles:
            continue
        if len(norms) != 1 or len(prior_articles) != 1 or prior_ambiguous:
            break
        new_article = bool(articles)
        return (q, norms, articles or prior_articles,
                incisos or (prior_incisos if not new_article and not numerals else set()),
                numerals or (prior_numerals if not new_article else set()), False)
    return parsed


def _marker(item):
    label = item["work"]["label"].casefold().strip()
    for prefix in ('literal ', 'inciso '):
        if label.startswith(prefix):
            label = label[len(prefix):].lstrip()
            break
    match = _LABEL_MARK.match(label)
    return match[1] if match else None


def _complete_list(parent, descendants, alphabetic):
    kind = {"inciso", "subinciso"} if alphabetic else {"numeral"}
    if not descendants or any(i["work"].get("kind") not in kind for i in descendants):
        return None
    markers = [_marker(i) for i in descendants]
    alphabet = ascii_lowercase.replace("n", "nñ") if "ñ" in markers else ascii_lowercase
    expected = (list(alphabet[:len(markers)]) if alphabetic
                else [str(i) for i in range(1, len(markers) + 1)])
    texts = [i["text"]["text"].strip() for i in descendants]
    parent_text = parent["text"]["text"].strip()
    body_markers = [m[1] for m in _PART_MARK.finditer(parent_text) if m[1].isalpha() == alphabetic]
    if markers == expected == body_markers and all(
        (m := _PART_MARK.match(text)) and m[1] == marker and text in parent_text
        for marker, text in zip(markers, texts)
    ):
        return texts
    return None


def resolve_reference(retriever, plan, parsed, *, heading_list=False):
    q, resources, articles, incisos, numerals, ambiguous = parsed
    number = articles[0][1]
    inciso = next(iter(incisos), None)
    numeral = next(iter(numerals), None)
    resource_id = next(iter(resources))
    result = {
        "engine": "sat", "state": "abstain", "reason": "unresolved_reference",
        "candidate_count": 0, "eligible_chunks": 0, "hits": [],
        "warning": "La referencia exacta no se pudo resolver de forma inequívoca en el corpus SAT.",
        "reference": {"resource_id": resource_id, "article": number,
                      "inciso": inciso, "numeral": numeral, "status": "unresolved"},
    }
    if ambiguous:
        return result
    eligible = {i["version"]["id"]: i for i in retriever.eligible(plan)}

    def children(item):
        return sorted(
            (eligible[k] for k in set(retriever.outgoing[(item["version"]["id"], "contains_version")])
             if k in eligible and eligible[k]["work"]["resource_id"] == resource_id),
            key=lambda i: (i["text"]["start"], i["version"]["id"]),
        )

    matches = [i for i in eligible.values() if i["work"].get("kind") == "article"
               and (m := _ARTICLE.match(fold(i["work"]["label"]).lstrip("# "))) and m[1] == number]
    if len(matches) != 1:
        return result
    target = matches[0]
    # A law can quote an article of a different code in its own modifying
    # article. Preserve this parent in the citation rather than attributing the
    # quoted article number directly to the amending instrument.
    parents = [eligible[e['source']] for e in retriever.edges
               if e['type'] == 'contains_version' and e['target'] == target['version']['id']
               and e['source'] in eligible
               and eligible[e['source']]['work'].get('kind') == 'article'
               and eligible[e['source']]['work']['resource_id'] == resource_id]
    def matching(parent, marker, kinds):
        return [i for i in children(parent) if i["work"].get("kind") in kinds and _marker(i) == marker]

    if inciso and numeral:
        routes = []
        for first, second, first_kinds, second_kinds in (
            (inciso, numeral, {"inciso"}, {"numeral", "subinciso"}),
            (numeral, inciso, {"numeral"}, {"inciso", "subinciso"}),
        ):
            for child in matching(target, first, first_kinds):
                routes.extend((node, first == numeral) for node in matching(child, second, second_kinds))
        if len(routes) != 1:
            return result
        target, numeral_first = routes[0]
    else:
        numeral_first = False
        if inciso or numeral:
            matches = matching(target, inciso or numeral,
                               {"inciso", "subinciso"} if inciso else {"numeral", "subinciso"})
            if len(matches) != 1:
                return result
            target = matches[0]

    label = {"ley": "Ley", "ds": "Decreto Supremo", "rm": "Resolución Ministerial"}
    _, kind, norm_number = resource_id.split(":")
    citation = f"Artículo {number.upper()} de la {label[kind]} {norm_number.upper()}" if kind != "ds" else (
        f"Artículo {number.upper()} del Decreto Supremo {norm_number.upper()}"
    )
    if len(parents) == 1:
        citation = (f"Artículo {number.upper()} (texto contenido en {parents[0]['work']['label']})"
                    f" — {label[kind]} {norm_number.upper()}")
    if numeral_first:
        citation += f", numeral {numeral}, literal {inciso}"
    elif inciso:
        citation += f", inciso {inciso})"
    if numeral and not numeral_first:
        citation += f", numeral {numeral}"

    def hit(item):
        text, version, work = item["text"], item["version"], item["work"]
        return {
            "id": "tu-ref:" + fingerprint([version["id"], text["id"]]),
            "content": text["text"], "score": 1.0, "work_id": work["id"],
            "version_id": version["id"], "resource_id": resource_id,
            "resource_label": retriever.nodes[resource_id].get("title", resource_id),
            "source_url": text["source_url"], "provenance_state": version["provenance_state"],
            "snapshot_as_of": version.get("snapshot_as_of"), "citation": citation,
        }

    # Use the complete CLV of the exact provision, never a ranked/truncated fragment.
    enumeration = None
    request = _ENUMERATE.search(q)
    if request or heading_list:
        alphabetic = heading_list if not request else request[1] in {"literales", "incisos"}
        texts = _complete_list(target, children(target), alphabetic)
        if alphabetic and not texts and not inciso:
            # An article can contain numerals; use a single eligible numbered branch
            # only if it accounts for every lettered item in the requested article.
            branches = [child for child in children(target) if child["work"].get("kind") == "numeral"
                        and any(m[1].isalpha() for m in _PART_MARK.finditer(child["text"]["text"]))]
            if len(branches) == 1:
                branch = branches[0]
                candidate = _complete_list(branch, children(branch), True)
                marks = [m[1] for m in _PART_MARK.finditer(target["text"]["text"]) if m[1].isalpha()]
                if candidate and marks == [_PART_MARK.match(text)[1] for text in candidate] and all(
                    text in target["text"]["text"] for text in candidate
                ):
                    texts = candidate
                    target = branch
                    numeral = _marker(branch)
                    citation += f", numeral {numeral}"
        if texts:
            enumeration = f"**{citation}:**\n\n" + "\n".join(
                text if text.startswith("- ") or not alphabetic else f"- {text}" for text in texts
            )
        elif alphabetic and not heading_list:
            return {**result, "warning": "No encontré una lista completa e inequívoca de literales en la referencia solicitada."}
    hits = [hit(target)]
    if sum(len(h["content"].encode()) for h in hits) > plan.context_bytes:
        return {**result, "reason": "complete_component_exceeds_budget",
                "warning": "La sección solicitada supera el presupuesto de contexto. Precisa un numeral o literal para recibir su texto completo; no se ha truncado la sección."}
    path = [label[kind] + " " + norm_number.upper()]
    if len(parents) == 1:
        path.append(parents[0]['work']['label'])
    path.append(f"Artículo {number.upper()}")
    if numeral_first:
        path += [f"Numeral {numeral}", f"Literal {inciso}"]
    else:
        if inciso:
            path.append(f"Inciso {inciso})")
        if numeral:
            path.append(f"Numeral {numeral}")
    hits[0]["sat_section"] = {
        "title": citation, "path": path, "version_id": hits[0]["version_id"],
        "source_url": hits[0]["source_url"],
    }
    return {**result, "state": "retrieved", "reason": None, "warning": None,
            "eligible_chunks": len(eligible), "candidate_count": len(hits), "hits": hits,
            "reference": {**result["reference"], "status": "exact", "citation": citation, "numeral": numeral},
            "verbatim_answer": enumeration}
