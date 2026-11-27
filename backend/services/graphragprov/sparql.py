"""Pure-Python SPARQL SELECT parser and N[X] how-provenance semiring evaluator."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
import time
from typing import Any, Literal

from services.graphragprov.models import (
    EvalLimits,
    GroundedGraph,
    NUMERIC_DATATYPES,
    ProvenanceRow,
    RDFTerm,
    RDF_TYPE_IRI,
    SparqlEvalResult,
    SparqlQuery,
    StatementOccurrence,
    XSD_BOOLEAN_IRI,
    XSD_DECIMAL_IRI,
    XSD_DOUBLE_IRI,
    XSD_INTEGER_IRI,
    XSD_STRING_IRI,
)
from services.graphragprov.semiring import (
    ProvExpr,
    atom,
    expand_to_polynomial,
    one,
    semiring_add,
    semiring_mul,
    zero,
)


class SparqlSyntaxError(ValueError):
    """Raised when a SPARQL query fails lexing or grammar parsing."""


class SparqlSafetyError(ValueError):
    """Raised when a SPARQL query violates safety bounds or attempts mutation."""


_MUTATION_KEYWORDS = frozenset({
    "INSERT",
    "DELETE",
    "DROP",
    "CLEAR",
    "LOAD",
    "CREATE",
    "COPY",
    "MOVE",
    "ADD",
})

_UNSUPPORTED_FORMS = frozenset({"CONSTRUCT", "ASK", "DESCRIBE"})

_NESTED_QUANTIFIER_RE = re.compile(r"\((?:[^()\\]|\\.)*[+*](?:[^()\\]|\\.)*\)[+*?{]")



@dataclass(frozen=True, slots=True)
class VarNode:
    name: str


@dataclass(frozen=True, slots=True)
class TermNode:
    term: RDFTerm


TermOrVar = VarNode | TermNode


@dataclass(frozen=True, slots=True)
class TriplePattern:
    subject: TermOrVar
    predicate: TermOrVar
    object: TermOrVar


class GraphPattern:
    """Base SPARQL graph pattern node."""


@dataclass(frozen=True, slots=True)
class BgpPattern(GraphPattern):
    triples: tuple[TriplePattern, ...]


@dataclass(frozen=True, slots=True)
class JoinPattern(GraphPattern):
    left: GraphPattern
    right: GraphPattern


@dataclass(frozen=True, slots=True)
class OptionalPattern(GraphPattern):
    left: GraphPattern
    right: GraphPattern


@dataclass(frozen=True, slots=True)
class UnionPattern(GraphPattern):
    branches: tuple[GraphPattern, ...]


@dataclass(frozen=True, slots=True)
class FilterPattern(GraphPattern):
    inner: GraphPattern
    expr: FilterExpr


class FilterExpr:
    """Base SPARQL FILTER expression node."""


@dataclass(frozen=True, slots=True)
class FilterVar(FilterExpr):
    name: str


@dataclass(frozen=True, slots=True)
class FilterConst(FilterExpr):
    term: RDFTerm


@dataclass(frozen=True, slots=True)
class FilterUnary(FilterExpr):
    op: Literal["!"]
    operand: FilterExpr


@dataclass(frozen=True, slots=True)
class FilterBinary(FilterExpr):
    op: str
    left: FilterExpr
    right: FilterExpr


@dataclass(frozen=True, slots=True)
class FilterCall(FilterExpr):
    name: str
    args: tuple[FilterExpr, ...]



@dataclass(frozen=True, slots=True)
class _Tok:
    kind: str
    value: str
    pos: int


_LEX_SPEC = re.compile(
    r"""
    (?P<WS>\s+)
    | (?P<COMMENT>\#[^\n]*)
    | (?P<IRI><[^<>\s"{}|^`\\]*>)
    | (?P<VAR>[?$][A-Za-z_][A-Za-z0-9_]*)
    | (?P<BNODE>_:[A-Za-z0-9_.\-]+)
    | (?P<DQUOTE>"(?:\\.|[^"\\])*")
    | (?P<SQUOTE>'(?:\\.|[^'\\])*')
    | (?P<LANG>@[A-Za-z]+(?:-[A-Za-z0-9]+)*)
    | (?P<DTYPE>\^\^)
    | (?P<OP>&&|\|\||!=|<=|>=|[=<>!])
    | (?P<PUNCT>[{}().,;*])
    | (?P<PNAME>[A-Za-z_][A-Za-z0-9_\-]*:[A-Za-z0-9_\-]*|:[A-Za-z0-9_\-]+)
    | (?P<NUMBER>-?\d+(?:\.\d+)?)
    | (?P<WORD>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)


def _unescape_string(raw: str) -> str:
    body = raw[1:-1]
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "\\" and i + 1 < n:
            nxt = body[i + 1]
            mapping = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "'": "'", "\\": "\\"}
            out.append(mapping.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _tokenize(query: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    pos = 0
    length = len(query)
    while pos < length:
        match = _LEX_SPEC.match(query, pos)
        if not match:
            snippet = query[pos : pos + 20]
            raise SparqlSyntaxError(f"Unexpected syntax near {snippet!r} at offset {pos}")
        kind = match.lastgroup or ""
        val = match.group(kind)
        if kind not in ("WS", "COMMENT"):
            tokens.append(_Tok(kind=kind, value=val, pos=pos))
        pos = match.end()
    return tokens



def parse_sparql(query: str, *, limits: EvalLimits = EvalLimits()) -> SparqlQuery:
    """Parse a SPARQL SELECT query string into a typed SparqlQuery AST."""
    if not query or not query.strip():
        raise SparqlSyntaxError("SPARQL query cannot be empty")
    tokens = _tokenize(query)
    if not tokens:
        raise SparqlSyntaxError("SPARQL query cannot be empty")

    for tok in tokens:
        if tok.kind == "WORD" and tok.value.upper() in _MUTATION_KEYWORDS:
            raise SparqlSafetyError(
                f"Read-only SPARQL engine rejects mutation keyword {tok.value.upper()!r}"
            )

    idx = 0
    prefixes: dict[str, str] = {}

    def peek(offset: int = 0) -> _Tok | None:
        pos = idx + offset
        return tokens[pos] if pos < len(tokens) else None

    def consume(expected_kind: str | None = None, expected_val: str | None = None) -> _Tok:
        nonlocal idx
        tok = peek()
        if tok is None:
            raise SparqlSyntaxError("Unexpected end of SPARQL query")
        if expected_kind is not None and tok.kind != expected_kind:
            raise SparqlSyntaxError(
                f"Expected {expected_kind} but found {tok.value!r} at offset {tok.pos}"
            )
        if expected_val is not None and tok.value.upper() != expected_val.upper():
            raise SparqlSyntaxError(
                f"Expected {expected_val!r} but found {tok.value!r} at offset {tok.pos}"
            )
        idx += 1
        return tok

    def is_kw(word: str, offset: int = 0) -> bool:
        tok = peek(offset)
        return tok is not None and tok.kind == "WORD" and tok.value.upper() == word

    def resolve_pname(pname: str, pos: int) -> str:
        prefix, local = pname.split(":", 1)
        if prefix not in prefixes:
            raise SparqlSyntaxError(f"Undeclared SPARQL prefix {prefix + ':'!r} at offset {pos}")
        return prefixes[prefix] + local

    def parse_term_or_var(*, allow_a: bool = False) -> TermOrVar:
        tok = peek()
        if tok is None:
            raise SparqlSyntaxError("Expected RDF term or variable")
        if tok.kind == "VAR":
            consume()
            return VarNode(tok.value[1:])
        if allow_a and tok.kind == "WORD" and tok.value == "a":
            consume()
            return TermNode(RDFTerm(kind="iri", value=RDF_TYPE_IRI, label="rdf:type"))
        if tok.kind == "IRI":
            consume()
            iri = tok.value[1:-1]
            return TermNode(RDFTerm(kind="iri", value=iri, label=iri))
        if tok.kind == "PNAME":
            consume()
            iri = resolve_pname(tok.value, tok.pos)
            return TermNode(RDFTerm(kind="iri", value=iri, label=tok.value))
        if tok.kind == "BNODE":
            consume()
            return TermNode(RDFTerm(kind="bnode", value=tok.value, label=tok.value))
        if tok.kind in ("DQUOTE", "SQUOTE"):
            consume()
            text_val = _unescape_string(tok.value)
            lang: str | None = None
            dtype: str | None = None
            nxt = peek()
            if nxt is not None and nxt.kind == "LANG":
                lang = consume().value[1:].lower()
            elif nxt is not None and nxt.kind == "DTYPE":
                consume()
                dt_tok = peek()
                if dt_tok is None:
                    raise SparqlSyntaxError("Expected datatype IRI after ^^")
                if dt_tok.kind == "IRI":
                    dtype = consume().value[1:-1]
                elif dt_tok.kind == "PNAME":
                    dt_p = consume()
                    dtype = resolve_pname(dt_p.value, dt_p.pos)
                else:
                    raise SparqlSyntaxError(f"Invalid datatype token {dt_tok.value!r}")
            return TermNode(
                RDFTerm(
                    kind="literal",
                    value=text_val,
                    label=text_val,
                    datatype=dtype,
                    language=lang,
                )
            )
        if tok.kind == "NUMBER":
            consume()
            dtype = XSD_DECIMAL_IRI if "." in tok.value else XSD_INTEGER_IRI
            return TermNode(RDFTerm(kind="literal", value=tok.value, label=tok.value, datatype=dtype))
        if tok.kind == "WORD" and tok.value.lower() in ("true", "false"):
            consume()
            val = tok.value.lower()
            return TermNode(
                RDFTerm(kind="literal", value=val, label=val, datatype=XSD_BOOLEAN_IRI)
            )
        raise SparqlSyntaxError(f"Unexpected term token {tok.value!r} at offset {tok.pos}")


    def parse_filter_expr(depth: int) -> FilterExpr:
        if depth > limits.max_ast_depth:
            raise SparqlSafetyError("SPARQL FILTER expression exceeds max AST depth")
        return parse_or(depth)

    def parse_or(depth: int) -> FilterExpr:
        left = parse_and(depth + 1)
        while peek() and peek().kind == "OP" and peek().value == "||":
            consume()
            right = parse_and(depth + 1)
            left = FilterBinary("||", left, right)
        return left

    def parse_and(depth: int) -> FilterExpr:
        left = parse_unary(depth + 1)
        while peek() and peek().kind == "OP" and peek().value == "&&":
            consume()
            right = parse_unary(depth + 1)
            left = FilterBinary("&&", left, right)
        return left

    def parse_unary(depth: int) -> FilterExpr:
        if peek() and peek().kind == "OP" and peek().value == "!":
            consume()
            return FilterUnary("!", parse_unary(depth + 1))
        return parse_comparison(depth + 1)

    def parse_comparison(depth: int) -> FilterExpr:
        left = parse_primary(depth + 1)
        tok = peek()
        if tok and tok.kind == "OP" and tok.value in ("=", "!=", "<", "<=", ">", ">="):
            op = consume().value
            right = parse_primary(depth + 1)
            return FilterBinary(op, left, right)
        return left

    def parse_primary(depth: int) -> FilterExpr:
        if depth > limits.max_ast_depth:
            raise SparqlSafetyError("SPARQL FILTER expression exceeds max AST depth")
        tok = peek()
        if tok is None:
            raise SparqlSyntaxError("Unexpected end inside FILTER expression")
        if tok.kind == "PUNCT" and tok.value == "(":
            consume()
            inner = parse_filter_expr(depth + 1)
            consume("PUNCT", ")")
            return inner
        if tok.kind == "WORD":
            nxt = peek(1)
            if nxt is not None and nxt.kind == "PUNCT" and nxt.value == "(":
                fn_name = consume().value.upper()
                consume("PUNCT", "(")
                args: list[FilterExpr] = []
                if not (peek() and peek().kind == "PUNCT" and peek().value == ")"):
                    args.append(parse_filter_expr(depth + 1))
                    while peek() and peek().kind == "PUNCT" and peek().value == ",":
                        consume()
                        args.append(parse_filter_expr(depth + 1))
                consume("PUNCT", ")")
                if fn_name == "REGEX" and len(args) >= 2 and isinstance(args[1], FilterConst):
                    pat = args[1].term.value
                    if len(pat) > limits.max_regex_len:
                        raise SparqlSafetyError(
                            f"REGEX pattern length {len(pat)} exceeds limit {limits.max_regex_len}"
                        )
                    if _NESTED_QUANTIFIER_RE.search(pat):
                        raise SparqlSafetyError("Potentially unsafe nested-quantifier REGEX rejected")
                return FilterCall(fn_name, tuple(args))
        term_or_var = parse_term_or_var(allow_a=False)
        if isinstance(term_or_var, VarNode):
            return FilterVar(term_or_var.name)
        return FilterConst(term_or_var.term)


    def parse_group_pattern(depth: int) -> GraphPattern:
        if depth > limits.max_ast_depth:
            raise SparqlSafetyError("SPARQL graph pattern exceeds max AST depth")
        consume("PUNCT", "{")
        current: GraphPattern | None = None
        pending_triples: list[TriplePattern] = []
        filters: list[FilterExpr] = []

        def flush_triples() -> None:
            nonlocal current, pending_triples
            if not pending_triples:
                return
            bgp = BgpPattern(tuple(pending_triples))
            pending_triples = []
            current = bgp if current is None else JoinPattern(current, bgp)

        while True:
            tok = peek()
            if tok is None:
                raise SparqlSyntaxError("Unclosed '{' in WHERE clause")
            if tok.kind == "PUNCT" and tok.value == "}":
                consume()
                break
            if tok.kind == "PUNCT" and tok.value == ".":
                consume()
                continue
            if is_kw("FILTER"):
                consume()
                if peek() and peek().kind == "PUNCT" and peek().value == "(":
                    consume()
                    fexpr = parse_filter_expr(depth + 1)
                    consume("PUNCT", ")")
                else:
                    fexpr = parse_primary(depth + 1)
                filters.append(fexpr)
                continue
            if is_kw("OPTIONAL"):
                flush_triples()
                consume()
                opt_right = parse_group_pattern(depth + 1)
                left_pat = current if current is not None else BgpPattern(())
                current = OptionalPattern(left_pat, opt_right)
                continue
            if tok.kind == "PUNCT" and tok.value == "{":
                flush_triples()
                first_branch = parse_group_pattern(depth + 1)
                if is_kw("UNION"):
                    branches: list[GraphPattern] = [first_branch]
                    while is_kw("UNION"):
                        consume()
                        branches.append(parse_group_pattern(depth + 1))
                    block: GraphPattern = UnionPattern(tuple(branches))
                else:
                    block = first_branch
                current = block if current is None else JoinPattern(current, block)
                continue

            # Parse triple pattern with `;` and `,` shorthands.
            subj = parse_term_or_var(allow_a=False)
            while True:
                pred = parse_term_or_var(allow_a=True)
                while True:
                    obj = parse_term_or_var(allow_a=False)
                    pending_triples.append(TriplePattern(subj, pred, obj))
                    if peek() and peek().kind == "PUNCT" and peek().value == ",":
                        consume()
                        continue
                    break
                if peek() and peek().kind == "PUNCT" and peek().value == ";":
                    consume()
                    nxt = peek()
                    if nxt and nxt.kind == "PUNCT" and nxt.value in (".", "}"):
                        break
                    continue
                break
            if peek() and peek().kind == "PUNCT" and peek().value == ".":
                consume()

        flush_triples()
        result: GraphPattern = current if current is not None else BgpPattern(())
        for fexpr in filters:
            result = FilterPattern(result, fexpr)
        return result

    while is_kw("PREFIX"):
        consume()
        p_tok = consume("PNAME")
        prefix_name, remainder = p_tok.value.split(":", 1)
        if remainder != "":
            raise SparqlSyntaxError(f"PREFIX label must end with ':', got {p_tok.value!r}")
        iri_tok = consume("IRI")
        prefixes[prefix_name] = iri_tok.value[1:-1]

    if peek() and peek().kind == "WORD" and peek().value.upper() in _UNSUPPORTED_FORMS:
        raise SparqlSyntaxError(
            f"Only SPARQL SELECT queries are supported (found {peek().value.upper()})"
        )

    consume("WORD", "SELECT")
    distinct = False
    if is_kw("DISTINCT"):
        consume()
        distinct = True

    projection: tuple[str, ...] | None
    if peek() and peek().kind == "PUNCT" and peek().value == "*":
        consume()
        projection = None
    else:
        proj_vars: list[str] = []
        while peek() and peek().kind == "VAR":
            var_name = consume().value[1:]
            if var_name not in proj_vars:
                proj_vars.append(var_name)
        if not proj_vars:
            raise SparqlSyntaxError("SELECT requires '*' or at least one ?variable")
        projection = tuple(proj_vars)

    if is_kw("WHERE"):
        consume()

    where_pattern = parse_group_pattern(0)

    order_by: list[tuple[str, Literal["ASC", "DESC"]]] = []
    limit: int | None = None
    offset = 0

    while peek() is not None:
        if is_kw("ORDER"):
            consume()
            consume("WORD", "BY")
            while peek() is not None:
                if is_kw("ASC") or is_kw("DESC"):
                    direction: Literal["ASC", "DESC"] = "ASC" if consume().value.upper() == "ASC" else "DESC"
                    consume("PUNCT", "(")
                    v_tok = consume("VAR")
                    consume("PUNCT", ")")
                    order_by.append((v_tok.value[1:], direction))
                elif peek().kind == "VAR":
                    v_tok = consume("VAR")
                    order_by.append((v_tok.value[1:], "ASC"))
                else:
                    break
            if not order_by:
                raise SparqlSyntaxError("ORDER BY requires at least one ?variable")
        elif is_kw("LIMIT"):
            consume()
            n_tok = consume("NUMBER")
            if "." in n_tok.value or int(n_tok.value) < 0:
                raise SparqlSyntaxError("LIMIT must be a non-negative integer")
            limit = int(n_tok.value)
        elif is_kw("OFFSET"):
            consume()
            n_tok = consume("NUMBER")
            if "." in n_tok.value or int(n_tok.value) < 0:
                raise SparqlSyntaxError("OFFSET must be a non-negative integer")
            offset = int(n_tok.value)
        else:
            bad = peek()
            raise SparqlSyntaxError(f"Unexpected trailing token {bad.value!r} at offset {bad.pos}")

    return SparqlQuery(
        prefixes=prefixes,
        distinct=distinct,
        projection=projection,
        where=where_pattern,
        order_by=tuple(order_by),
        limit=limit,
        offset=offset,
    )



def _collect_vars(pattern: GraphPattern, out: list[str]) -> None:
    def add_var(node: TermOrVar) -> None:
        if isinstance(node, VarNode) and node.name not in out:
            out.append(node.name)

    if isinstance(pattern, BgpPattern):
        for tp in pattern.triples:
            add_var(tp.subject)
            add_var(tp.predicate)
            add_var(tp.object)
    elif isinstance(pattern, (JoinPattern, OptionalPattern)):
        _collect_vars(pattern.left, out)
        _collect_vars(pattern.right, out)
    elif isinstance(pattern, UnionPattern):
        for br in pattern.branches:
            _collect_vars(br, out)
    elif isinstance(pattern, FilterPattern):
        _collect_vars(pattern.inner, out)


def _binding_key(
    binding: dict[str, RDFTerm | None],
    variables: tuple[str, ...],
) -> tuple[tuple[str, tuple[str, str, str | None, str | None] | None], ...]:
    return tuple(
        (var, binding[var].term_key() if binding.get(var) is not None else None)
        for var in variables
    )


def _compatible(a: dict[str, RDFTerm | None], b: dict[str, RDFTerm | None]) -> bool:
    for var, val_a in a.items():
        if val_a is None:
            continue
        val_b = b.get(var)
        if val_b is not None and val_a.term_key() != val_b.term_key():
            return False
    return True


def _merge_bindings(
    a: dict[str, RDFTerm | None], b: dict[str, RDFTerm | None]
) -> dict[str, RDFTerm | None]:
    merged = dict(a)
    for var, val in b.items():
        if val is not None or var not in merged:
            merged[var] = val
    return merged


def _as_number(term: RDFTerm | None) -> float | None:
    if term is None or term.kind != "literal":
        return None
    if term.datatype in NUMERIC_DATATYPES:
        try:
            return float(term.value)
        except ValueError:
            return None
    return None


def _ebv(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    if isinstance(val, RDFTerm):
        if val.kind != "literal":
            return True
        if val.datatype == XSD_BOOLEAN_IRI:
            return val.value.lower() == "true"
        num = _as_number(val)
        if num is not None:
            return num != 0.0
        return len(val.value) > 0
    return bool(val)


def _to_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, RDFTerm):
        return val.value
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def _eval_filter(
    expr: FilterExpr,
    binding: dict[str, RDFTerm | None],
    limits: EvalLimits,
) -> Any:
    if isinstance(expr, FilterVar):
        return binding.get(expr.name)
    if isinstance(expr, FilterConst):
        return expr.term
    if isinstance(expr, FilterUnary):
        return not _ebv(_eval_filter(expr.operand, binding, limits))
    if isinstance(expr, FilterBinary):
        if expr.op == "&&":
            return _ebv(_eval_filter(expr.left, binding, limits)) and _ebv(
                _eval_filter(expr.right, binding, limits)
            )
        if expr.op == "||":
            return _ebv(_eval_filter(expr.left, binding, limits)) or _ebv(
                _eval_filter(expr.right, binding, limits)
            )
        left = _eval_filter(expr.left, binding, limits)
        right = _eval_filter(expr.right, binding, limits)
        if left is None or right is None:
            return False
        if isinstance(left, RDFTerm) and isinstance(right, RDFTerm):
            l_num = _as_number(left)
            r_num = _as_number(right)
            if l_num is not None and r_num is not None:
                l_cmp: Any = l_num
                r_cmp: Any = r_num
            elif expr.op in ("=", "!="):
                if left.kind == "literal" and right.kind == "literal":
                    l_cmp, r_cmp = left.value, right.value
                else:
                    l_cmp, r_cmp = left.term_key(), right.term_key()
            else:
                l_cmp, r_cmp = left.value, right.value
        else:
            l_cmp, r_cmp = _to_str(left), _to_str(right)
        if expr.op == "=":
            return l_cmp == r_cmp
        if expr.op == "!=":
            return l_cmp != r_cmp
        if expr.op == "<":
            return l_cmp < r_cmp
        if expr.op == "<=":
            return l_cmp <= r_cmp
        if expr.op == ">":
            return l_cmp > r_cmp
        if expr.op == ">=":
            return l_cmp >= r_cmp
        raise SparqlSyntaxError(f"Unsupported binary operator {expr.op!r}")

    if isinstance(expr, FilterCall):
        name = expr.name
        if name == "BOUND":
            if len(expr.args) != 1 or not isinstance(expr.args[0], FilterVar):
                raise SparqlSyntaxError("BOUND() expects a single ?variable")
            return binding.get(expr.args[0].name) is not None
        evaluated = [_eval_filter(arg, binding, limits) for arg in expr.args]
        if name == "STR":
            if len(evaluated) != 1:
                raise SparqlSyntaxError("STR() expects 1 argument")
            text = _to_str(evaluated[0])
            return RDFTerm(kind="literal", value=text, label=text, datatype=XSD_STRING_IRI)
        if name == "LCASE":
            if len(evaluated) != 1:
                raise SparqlSyntaxError("LCASE() expects 1 argument")
            text = _to_str(evaluated[0]).lower()
            return RDFTerm(kind="literal", value=text, label=text, datatype=XSD_STRING_IRI)
        if name == "UCASE":
            if len(evaluated) != 1:
                raise SparqlSyntaxError("UCASE() expects 1 argument")
            text = _to_str(evaluated[0]).upper()
            return RDFTerm(kind="literal", value=text, label=text, datatype=XSD_STRING_IRI)
        if name == "CONTAINS":
            if len(evaluated) != 2:
                raise SparqlSyntaxError("CONTAINS() expects 2 arguments")
            return _to_str(evaluated[1]) in _to_str(evaluated[0])
        if name == "STRSTARTS":
            if len(evaluated) != 2:
                raise SparqlSyntaxError("STRSTARTS() expects 2 arguments")
            return _to_str(evaluated[0]).startswith(_to_str(evaluated[1]))
        if name == "STRENDS":
            if len(evaluated) != 2:
                raise SparqlSyntaxError("STRENDS() expects 2 arguments")
            return _to_str(evaluated[0]).endswith(_to_str(evaluated[1]))
        if name == "REGEX":
            if len(evaluated) not in (2, 3):
                raise SparqlSyntaxError("REGEX() expects 2 or 3 arguments")
            target = _to_str(evaluated[0])
            pat = _to_str(evaluated[1])
            if len(pat) > limits.max_regex_len:
                raise SparqlSafetyError("REGEX pattern exceeds safety length")
            if _NESTED_QUANTIFIER_RE.search(pat):
                raise SparqlSafetyError("Unsafe nested-quantifier REGEX pattern rejected")
            flags_str = _to_str(evaluated[2]) if len(evaluated) == 3 else ""
            flags = 0
            if "i" in flags_str:
                flags |= re.IGNORECASE
            if "m" in flags_str:
                flags |= re.MULTILINE
            if "s" in flags_str:
                flags |= re.DOTALL
            try:
                return bool(re.search(pat, target, flags))
            except re.error as exc:
                raise SparqlSyntaxError(f"Invalid REGEX pattern: {exc}") from exc
        if name in ("ISIRI", "ISURI"):
            if len(evaluated) != 1:
                raise SparqlSyntaxError(f"{name}() expects 1 argument")
            return isinstance(evaluated[0], RDFTerm) and evaluated[0].kind == "iri"
        if name == "ISLITERAL":
            if len(evaluated) != 1:
                raise SparqlSyntaxError("ISLITERAL() expects 1 argument")
            return isinstance(evaluated[0], RDFTerm) and evaluated[0].kind == "literal"
        if name == "LANG":
            if len(evaluated) != 1:
                raise SparqlSyntaxError("LANG() expects 1 argument")
            val = evaluated[0]
            lang = val.language if isinstance(val, RDFTerm) and val.language else ""
            return RDFTerm(kind="literal", value=lang, label=lang or "none", datatype=XSD_STRING_IRI)
        if name == "DATATYPE":
            if len(evaluated) != 1:
                raise SparqlSyntaxError("DATATYPE() expects 1 argument")
            val = evaluated[0]
            if not isinstance(val, RDFTerm) or val.kind != "literal":
                return None
            dt = val.datatype or (
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString"
                if val.language
                else XSD_STRING_IRI
            )
            return RDFTerm(kind="iri", value=dt, label=dt)
        raise SparqlSyntaxError(f"Unsupported FILTER function {name!r}")

    raise SparqlSyntaxError(f"Unsupported FILTER expression node: {type(expr).__name__}")


def _terms_equal_for_pattern(occ_term: RDFTerm, pat_term: RDFTerm) -> bool:
    if occ_term.kind != pat_term.kind:
        return False
    if occ_term.kind != "literal":
        return occ_term.value == pat_term.value
    if occ_term.value != pat_term.value:
        return False
    if pat_term.language is not None and occ_term.language != pat_term.language:
        return False
    if pat_term.datatype is not None and occ_term.datatype != pat_term.datatype:
        return False
    return True


class _OccurrenceIndex:
    """Hash index over a GroundedGraph's StatementOccurrences for fast BGP probes."""

    def __init__(self, occurrences: tuple[StatementOccurrence, ...]) -> None:
        self.all = occurrences
        self.by_s: dict[str, list[StatementOccurrence]] = defaultdict(list)
        self.by_p: dict[str, list[StatementOccurrence]] = defaultdict(list)
        self.by_o: dict[str, list[StatementOccurrence]] = defaultdict(list)
        self.by_sp: dict[tuple[str, str], list[StatementOccurrence]] = defaultdict(list)
        self.by_po: dict[tuple[str, str], list[StatementOccurrence]] = defaultdict(list)
        self.by_so: dict[tuple[str, str], list[StatementOccurrence]] = defaultdict(list)
        for occ in occurrences:
            s_val, p_val, o_val = occ.subject.value, occ.predicate.value, occ.object.value
            self.by_s[s_val].append(occ)
            self.by_p[p_val].append(occ)
            self.by_o[o_val].append(occ)
            self.by_sp[(s_val, p_val)].append(occ)
            self.by_po[(p_val, o_val)].append(occ)
            self.by_so[(s_val, o_val)].append(occ)

    def candidates(
        self,
        s_term: RDFTerm | None,
        p_term: RDFTerm | None,
        o_term: RDFTerm | None,
    ) -> list[StatementOccurrence] | tuple[StatementOccurrence, ...]:
        if s_term is not None and p_term is not None:
            return self.by_sp.get((s_term.value, p_term.value), ())
        if p_term is not None and o_term is not None:
            return self.by_po.get((p_term.value, o_term.value), ())
        if s_term is not None and o_term is not None:
            return self.by_so.get((s_term.value, o_term.value), ())
        if p_term is not None:
            return self.by_p.get(p_term.value, ())
        if s_term is not None:
            return self.by_s.get(s_term.value, ())
        if o_term is not None:
            return self.by_o.get(o_term.value, ())
        return self.all


def _sort_key_for_term(term: RDFTerm | None) -> tuple[int, float | str]:
    if term is None:
        return (2, "")
    num = _as_number(term)
    if num is not None:
        return (0, num)
    return (1, term.value.casefold())


def evaluate_sparql(
    graph: GroundedGraph,
    query: SparqlQuery | str,
    *,
    limits: EvalLimits = EvalLimits(),
) -> SparqlEvalResult:
    """Evaluate a parsed (or raw) SPARQL SELECT query over `graph` with N[X] provenance."""
    started = time.perf_counter()
    ast = parse_sparql(query, limits=limits) if isinstance(query, str) else query
    index = _OccurrenceIndex(graph.occurrences)
    work_counter = 0

    def bump_work(amount: int = 1) -> None:
        nonlocal work_counter
        work_counter += amount
        if work_counter > limits.max_join_work:
            raise SparqlSafetyError(
                f"SPARQL evaluation exceeded safety work budget ({limits.max_join_work} steps)"
            )

    def match_triple_against_seed(
        tp: TriplePattern,
        seed_rows: list[tuple[dict[str, RDFTerm | None], ProvExpr]],
    ) -> list[tuple[dict[str, RDFTerm | None], ProvExpr]]:
        results: list[tuple[dict[str, RDFTerm | None], ProvExpr]] = []
        for binding, prov in seed_rows:
            s_bound = (
                tp.subject.term
                if isinstance(tp.subject, TermNode)
                else binding.get(tp.subject.name)
            )
            p_bound = (
                tp.predicate.term
                if isinstance(tp.predicate, TermNode)
                else binding.get(tp.predicate.name)
            )
            o_bound = (
                tp.object.term
                if isinstance(tp.object, TermNode)
                else binding.get(tp.object.name)
            )
            for occ in index.candidates(s_bound, p_bound, o_bound):
                bump_work()
                if s_bound is not None and not _terms_equal_for_pattern(occ.subject, s_bound):
                    continue
                if p_bound is not None and not _terms_equal_for_pattern(occ.predicate, p_bound):
                    continue
                if o_bound is not None and not _terms_equal_for_pattern(occ.object, o_bound):
                    continue
                new_b = dict(binding)
                ok = True
                for slot, occ_term in (
                    (tp.subject, occ.subject),
                    (tp.predicate, occ.predicate),
                    (tp.object, occ.object),
                ):
                    if isinstance(slot, VarNode):
                        existing = new_b.get(slot.name)
                        if existing is not None and existing.term_key() != occ_term.term_key():
                            ok = False
                            break
                        new_b[slot.name] = occ_term
                if ok:
                    results.append((new_b, semiring_mul(prov, atom(occ.token))))
        return results

    def eval_pattern(
        pattern: GraphPattern,
        seed: list[tuple[dict[str, RDFTerm | None], ProvExpr]] | None = None,
    ) -> list[tuple[dict[str, RDFTerm | None], ProvExpr]]:
        if isinstance(pattern, BgpPattern):
            stream = list(seed) if seed is not None else [({}, one())]
            for tp in pattern.triples:
                stream = match_triple_against_seed(tp, stream)
                if not stream:
                    return []
            return stream

        if isinstance(pattern, JoinPattern):
            left_rows = eval_pattern(pattern.left, seed)
            if not left_rows:
                return []
            right_rows = eval_pattern(pattern.right, None)
            if not right_rows:
                return []
            out: list[tuple[dict[str, RDFTerm | None], ProvExpr]] = []
            for b_l, p_l in left_rows:
                for b_r, p_r in right_rows:
                    bump_work()
                    if _compatible(b_l, b_r):
                        out.append((_merge_bindings(b_l, b_r), semiring_mul(p_l, p_r)))
            return out

        if isinstance(pattern, UnionPattern):
            out = []
            for branch in pattern.branches:
                out.extend(eval_pattern(branch, seed))
            return out

        if isinstance(pattern, OptionalPattern):
            left_rows = eval_pattern(pattern.left, seed)
            if not left_rows:
                return []
            right_rows = eval_pattern(pattern.right, None)
            out = []
            for b_l, p_l in left_rows:
                matched_any = False
                for b_r, p_r in right_rows:
                    bump_work()
                    if _compatible(b_l, b_r):
                        out.append((_merge_bindings(b_l, b_r), semiring_mul(p_l, p_r)))
                        matched_any = True
                if not matched_any:
                    out.append((dict(b_l), semiring_mul(p_l, one())))
            return out

        if isinstance(pattern, FilterPattern):
            inner_rows = eval_pattern(pattern.inner, seed)
            return [
                (b, p)
                for b, p in inner_rows
                if _ebv(_eval_filter(pattern.expr, b, limits))
            ]

        raise SparqlSyntaxError(f"Unsupported graph pattern: {type(pattern).__name__}")

    raw_rows = eval_pattern(ast.where)

    if ast.projection is not None:
        variables = ast.projection
    else:
        found_vars: list[str] = []
        _collect_vars(ast.where, found_vars)
        variables = tuple(found_vars)

    grouped_bindings: dict[tuple, dict[str, RDFTerm | None]] = {}
    grouped_prov: dict[tuple, ProvExpr] = {}
    for binding, prov in raw_rows:
        projected = {var: binding.get(var) for var in variables}
        key = _binding_key(projected, variables)
        if key not in grouped_bindings:
            grouped_bindings[key] = projected
            grouped_prov[key] = prov
        else:
            grouped_prov[key] = semiring_add(grouped_prov[key], prov)

    ordered_keys = list(grouped_bindings.keys())
    if ast.order_by:
        for var_name, direction in reversed(ast.order_by):
            ordered_keys.sort(
                key=lambda k: _sort_key_for_term(grouped_bindings[k].get(var_name)),
                reverse=(direction == "DESC"),
            )

    if ast.offset:
        ordered_keys = ordered_keys[ast.offset :]

    effective_limit = limits.max_rows
    if ast.limit is not None:
        effective_limit = min(ast.limit, limits.max_rows)
    truncated_rows = len(ordered_keys) > effective_limit and (
        ast.limit is None or ast.limit > limits.max_rows
    )
    ordered_keys = ordered_keys[:effective_limit]

    rows: list[ProvenanceRow] = []
    referenced: set[str] = set()
    warnings: list[str] = []
    any_poly_truncated = False

    for key in ordered_keys:
        prov_expr = grouped_prov[key]
        poly = expand_to_polynomial(prov_expr, max_terms=limits.max_monomials)
        if poly.truncated:
            any_poly_truncated = True
        referenced.update(poly.witness_tokens)
        rows.append(
            ProvenanceRow(
                bindings=grouped_bindings[key],
                expr=prov_expr,
                polynomial=poly,
            )
        )

    if truncated_rows:
        warnings.append(f"Resultados truncados al límite seguro de {limits.max_rows} filas.")
    if any_poly_truncated:
        warnings.append(
            f"Uno o más polinomios excedieron {limits.max_monomials} monomios y fueron truncados."
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return SparqlEvalResult(
        variables=variables,
        rows=tuple(rows),
        referenced_tokens=tuple(sorted(referenced)),
        elapsed_ms=elapsed_ms,
        truncated_rows=truncated_rows,
        warnings=tuple(warnings),
    )
