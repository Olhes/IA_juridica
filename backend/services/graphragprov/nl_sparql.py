"""Deterministic Spanish NL-to-SPARQL compiler and optional Cohere translator."""
from __future__ import annotations

import re
import unicodedata

from services.graphragprov.models import DEFAULT_NAMESPACES, GroundedGraph
from services.graphragprov.sparql import SparqlSyntaxError, parse_sparql

SAT_NS = DEFAULT_NAMESPACES["sat"]
LEGAL_NS = DEFAULT_NAMESPACES["legal"]

PROVENANCE_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "obligations",
        "title": "Obligaciones legales",
        "description": "Lista sujetos y obligaciones extraídas con su polinomio de proveniencia.",
        "sparql": (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            f"PREFIX sat: <{SAT_NS}>\n"
            "SELECT DISTINCT ?sujeto ?obligacion ?encabezado WHERE {\n"
            "  ?sujeto legal:obligates ?obligacion .\n"
            "  OPTIONAL { ?sujeto sat:hasHeading ?encabezado . }\n"
            "}"
        ),
    },
    {
        "id": "deontic_union",
        "title": "Obligaciones y prohibiciones (UNION / ⊕)",
        "description": "Combina obligaciones y prohibiciones mostrando sumas (⊕) en N[X].",
        "sparql": (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?sujeto ?regla WHERE {\n"
            "  { ?sujeto legal:obligates ?regla . }\n"
            "  UNION\n"
            "  { ?sujeto legal:prohibits ?regla . }\n"
            "}"
        ),
    },
    {
        "id": "norm_references",
        "title": "Referencias y reformas normativas",
        "description": "Muestra citas, modificaciones, derogaciones e incorporaciones de normas.",
        "sparql": (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?componente ?norma WHERE {\n"
            "  { ?componente legal:cites ?norma . }\n"
            "  UNION\n"
            "  { ?componente legal:amends ?norma . }\n"
            "  UNION\n"
            "  { ?componente legal:repeals ?norma . }\n"
            "  UNION\n"
            "  { ?componente legal:incorporates ?norma . }\n"
            "}"
        ),
    },
    {
        "id": "deadlines",
        "title": "Plazos legales numéricos",
        "description": "Obtiene plazos legales en enteros XSD ordenados ascendentemente.",
        "sparql": (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?sujeto ?plazo WHERE {\n"
            "  ?sujeto legal:setsDeadline ?plazo .\n"
            "}\n"
            "ORDER BY ASC(?plazo)"
        ),
    },
    {
        "id": "structure_multihop",
        "title": "Estructura multi-salto (Join / ⊗)",
        "description": "Demuestra productos de proveniencia (⊗) en joins de componentes y encabezados.",
        "sparql": (
            f"PREFIX sat: <{SAT_NS}>\n"
            "SELECT DISTINCT ?norma ?componente ?encabezado WHERE {\n"
            "  ?norma sat:hasComponent ?componente .\n"
            "  ?componente sat:hasHeading ?encabezado .\n"
            "}"
        ),
    },
]

_ARTICLE_REF_RE = re.compile(r"\bart(?:iculo|s?\.?)?\s+(\d{1,4}(?:-[a-z])?|unico)\b")
_STOPWORDS = frozenset({
    "que", "cual", "cuales", "como", "donde", "quien", "quienes", "sobre", "para",
    "esta", "este", "estos", "estas", "una", "uno", "unos", "unas", "los", "las",
    "del", "con", "sin", "por", "norma", "ley", "establece", "dice", "indica",
    "muestra", "listar", "lista", "todos", "todas", "tiene", "tienen", "hay",
})
_JSON_FENCE_RE = re.compile(r"^```(?:sparql)?\s*|\s*```$", re.IGNORECASE)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").casefold()


def _escape_sparql_str(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def compile_nl_to_sparql_deterministic(
    question: str,
    graph: GroundedGraph,
) -> tuple[str, list[str]]:
    """Compile a Spanish legal question into a parser-verified SPARQL SELECT query."""
    if not question or not question.strip():
        raise SparqlSyntaxError("La pregunta en lenguaje natural no puede estar vacía")

    folded = _fold(question)
    warnings: list[str] = []
    article_m = _ARTICLE_REF_RE.search(folded)
    article_filter = ""
    if article_m:
        art_num = article_m.group(1)
        article_filter = (
            f'  FILTER (CONTAINS(LCASE(STR(?encabezado)), "artículo {art_num}") '
            f'|| CONTAINS(LCASE(STR(?encabezado)), "articulo {art_num}"))\n'
        )

    if any(w in folded for w in ("obligacion", "obliga", "deber", "deben", "debera")):
        if article_filter:
            sparql = (
                f"PREFIX legal: <{LEGAL_NS}>\n"
                f"PREFIX sat: <{SAT_NS}>\n"
                "SELECT DISTINCT ?sujeto ?obligacion ?encabezado WHERE {\n"
                "  ?sujeto legal:obligates ?obligacion .\n"
                "  ?sujeto sat:hasHeading ?encabezado .\n"
                f"{article_filter}"
                "}"
            )
        else:
            sparql = (
                f"PREFIX legal: <{LEGAL_NS}>\n"
                f"PREFIX sat: <{SAT_NS}>\n"
                "SELECT DISTINCT ?sujeto ?obligacion ?encabezado WHERE {\n"
                "  ?sujeto legal:obligates ?obligacion .\n"
                "  OPTIONAL { ?sujeto sat:hasHeading ?encabezado . }\n"
                "}"
            )
    elif any(w in folded for w in ("prohibicion", "prohibe", "prohibido", "no podra")):
        sparql = (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            f"PREFIX sat: <{SAT_NS}>\n"
            "SELECT DISTINCT ?sujeto ?prohibicion ?encabezado WHERE {\n"
            "  ?sujeto legal:prohibits ?prohibicion .\n"
            "  OPTIONAL { ?sujeto sat:hasHeading ?encabezado . }\n"
            f"{article_filter}"
            "}"
        )
    elif any(w in folded for w in ("plazo", "dias", "meses", "termino")):
        num_m = re.search(r"\b(\d{1,4})\b", folded)
        num_filter = ""
        if num_m and any(k in folded for k in ("menor", "hasta", "maximo")):
            num_filter = f"  FILTER (?plazo <= {int(num_m.group(1))})\n"
        elif num_m and any(k in folded for k in ("mayor", "mas de", "superior")):
            num_filter = f"  FILTER (?plazo >= {int(num_m.group(1))})\n"
        sparql = (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?sujeto ?plazo WHERE {\n"
            "  ?sujeto legal:setsDeadline ?plazo .\n"
            f"{num_filter}"
            "}\n"
            "ORDER BY ASC(?plazo)"
        )
    elif any(w in folded for w in ("definicion", "define", "concepto", "se entiende")):
        sparql = (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?sujeto ?definicion WHERE {\n"
            "  ?sujeto legal:defines ?definicion .\n"
            "}"
        )
    elif any(w in folded for w in ("cita", "referencia", "norma citada", "modifica", "deroga", "incorpora", "leyes")):
        sparql = (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?componente ?norma WHERE {\n"
            "  { ?componente legal:cites ?norma . }\n"
            "  UNION\n"
            "  { ?componente legal:amends ?norma . }\n"
            "  UNION\n"
            "  { ?componente legal:repeals ?norma . }\n"
            "  UNION\n"
            "  { ?componente legal:incorporates ?norma . }\n"
            "}"
        )
    elif any(w in folded for w in ("sancion", "multa", "infraccion", "pena")):
        sparql = (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?sujeto ?sancion WHERE {\n"
            "  ?sujeto legal:sanctions ?sancion .\n"
            "}"
        )
    elif any(w in folded for w in ("derecho", "garantiza")):
        sparql = (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?sujeto ?derecho WHERE {\n"
            "  ?sujeto legal:grantsRight ?derecho .\n"
            "}"
        )
    elif any(w in folded for w in ("competencia", "competente", "entidad", "administra", "supervisa", "encargado")):
        sparql = (
            f"PREFIX legal: <{LEGAL_NS}>\n"
            "SELECT DISTINCT ?sujeto ?competencia WHERE {\n"
            "  ?sujeto legal:assignsCompetence ?competencia .\n"
            "}"
        )
    elif any(w in folded for w in ("estructura", "jerarquia", "componentes", "multi-salto", "multisalto", "partes")):
        sparql = (
            f"PREFIX sat: <{SAT_NS}>\n"
            "SELECT DISTINCT ?norma ?componente ?encabezado WHERE {\n"
            "  ?norma sat:hasComponent ?componente .\n"
            "  ?componente sat:hasHeading ?encabezado .\n"
            f"{article_filter}"
            "}"
        )
    elif article_filter:
        sparql = (
            f"PREFIX sat: <{SAT_NS}>\n"
            "SELECT DISTINCT ?componente ?encabezado ?predicado ?valor WHERE {\n"
            "  ?componente sat:hasHeading ?encabezado .\n"
            "  ?componente ?predicado ?valor .\n"
            f"{article_filter}"
            "}"
        )
    else:
        keywords = [
            tok
            for tok in re.findall(r"[a-z0-9]{4,}", folded)
            if tok not in _STOPWORDS
        ][:2]
        if keywords:
            clauses = " || ".join(
                f'CONTAINS(LCASE(STR(?objeto)), "{_escape_sparql_str(kw)}")'
                for kw in keywords
            )
            sparql = (
                "SELECT DISTINCT ?sujeto ?predicado ?objeto WHERE {\n"
                "  ?sujeto ?predicado ?objeto .\n"
                f"  FILTER ({clauses})\n"
                "}"
            )
            warnings.append(
                "Pregunta traducida con filtro léxico genérico; edite el SPARQL para mayor precisión."
            )
        else:
            sparql = (
                f"PREFIX sat: <{SAT_NS}>\n"
                "SELECT DISTINCT ?norma ?componente ?encabezado WHERE {\n"
                "  ?norma sat:hasComponent ?componente .\n"
                "  ?componente sat:hasHeading ?encabezado .\n"
                "}"
            )
            warnings.append("Se aplicó consulta estructural por defecto.")

    parse_sparql(sparql)
    return sparql, warnings


async def compile_nl_to_sparql_cohere(
    question: str,
    graph: GroundedGraph,
    *,
    api_key: str,
    model: str,
) -> tuple[str, list[str]]:
    """Translate a Spanish question to SPARQL SELECT via CohereChat and validate with parse_sparql()."""
    if not api_key:
        raise ValueError("COHERE_API_KEY es requerida para compilación NL-a-SPARQL con Cohere")
    from services.cohere_chat import CohereChat

    prefix_lines = "\n".join(f"PREFIX {k}: <{v}>" for k, v in graph.namespaces.items())
    pred_list = ", ".join(graph.predicates[:25]) or "(none)"
    preamble = (
        "Translate the user's Spanish legal question into a single read-only SPARQL 1.1 SELECT query. "
        "Return ONLY the SPARQL query with PREFIX declarations. Never emit INSERT, DELETE, DROP, or prose."
    )
    message = (
        f"Available prefixes:\n{prefix_lines}\n\n"
        f"Available predicates in graph: {pred_list}\n\n"
        f"Question: {question}\n"
    )
    client = CohereChat(api_key)
    response = await client.chat(
        message=message,
        preamble=preamble,
        model=model,
        temperature=0.0,
    )
    sparql = _JSON_FENCE_RE.sub("", (response.text or "").strip()).strip()
    parse_sparql(sparql)
    return sparql, []
