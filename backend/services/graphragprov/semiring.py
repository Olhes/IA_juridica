"""Exact commutative N[X] how-provenance semiring and NPCS prefix codec."""
from __future__ import annotations

from dataclasses import dataclass
import re

MAX_PARSE_DEPTH = 64
MAX_SCALAR_EXPANSION = 1024

_SUPERSCRIPTS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:\-]*$")


def _superscript(exp: int) -> str:
    return str(exp).translate(_SUPERSCRIPTS)


class ProvExpr:
    """Base algebraic provenance expression over the commutative semiring N[X]."""


@dataclass(frozen=True, slots=True)
class ProvZero(ProvExpr):
    """Additive identity 0."""


@dataclass(frozen=True, slots=True)
class ProvOne(ProvExpr):
    """Multiplicative identity 1."""


@dataclass(frozen=True, slots=True)
class ProvAtom(ProvExpr):
    """Indeterminate occurrence variable token (e.g. occ_a1b2c3d4e5f6 or o1)."""

    token: str

    def __post_init__(self) -> None:
        if not self.token or not _TOKEN_RE.match(self.token):
            raise ValueError(f"Invalid provenance token: {self.token!r}")


@dataclass(frozen=True, slots=True)
class ProvAdd(ProvExpr):
    """Flattened n-ary disjunction / sum (⊕)."""

    terms: tuple[ProvExpr, ...]

    def __post_init__(self) -> None:
        if len(self.terms) < 2:
            raise ValueError("ProvAdd requires at least two terms")


@dataclass(frozen=True, slots=True)
class ProvMul(ProvExpr):
    """Flattened n-ary conjunction / product (⊗)."""

    factors: tuple[ProvExpr, ...]

    def __post_init__(self) -> None:
        if len(self.factors) < 2:
            raise ValueError("ProvMul requires at least two factors")


_ZERO = ProvZero()
_ONE = ProvOne()


def zero() -> ProvExpr:
    return _ZERO


def one() -> ProvExpr:
    return _ONE


def atom(token: str) -> ProvExpr:
    return ProvAtom(token)


def semiring_add(a: ProvExpr, b: ProvExpr) -> ProvExpr:
    """Combine two provenance expressions with additive disjunction ⊕."""
    if isinstance(a, ProvZero):
        return b
    if isinstance(b, ProvZero):
        return a
    left = a.terms if isinstance(a, ProvAdd) else (a,)
    right = b.terms if isinstance(b, ProvAdd) else (b,)
    return ProvAdd(left + right)


def semiring_mul(a: ProvExpr, b: ProvExpr) -> ProvExpr:
    """Combine two provenance expressions with multiplicative conjunction ⊗."""
    if isinstance(a, ProvZero) or isinstance(b, ProvZero):
        return _ZERO
    if isinstance(a, ProvOne):
        return b
    if isinstance(b, ProvOne):
        return a
    left = a.factors if isinstance(a, ProvMul) else (a,)
    right = b.factors if isinstance(b, ProvMul) else (b,)
    return ProvMul(left + right)


@dataclass(frozen=True, slots=True)
class Monomial:
    """Product term coeff * prod(token ** exp) in N[X], preserving multiplicity."""

    factors: tuple[tuple[str, int], ...]
    coeff: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.coeff, bool) or self.coeff < 1:
            raise ValueError("Monomial coeff must be a positive integer")
        prev: str | None = None
        for token, exp in self.factors:
            if not token:
                raise ValueError("Monomial factor token must be non-empty")
            if isinstance(exp, bool) or exp < 1:
                raise ValueError("Monomial factor exponent must be >= 1")
            if prev is not None and token <= prev:
                raise ValueError("Monomial factors must be strictly sorted and deduplicated")
            prev = token

    def mul(self, other: Monomial) -> Monomial:
        merged: dict[str, int] = dict(self.factors)
        for token, exp in other.factors:
            merged[token] = merged.get(token, 0) + exp
        return Monomial(
            factors=tuple(sorted(merged.items())),
            coeff=self.coeff * other.coeff,
        )

    def tokens(self) -> tuple[str, ...]:
        return tuple(token for token, _ in self.factors)

    def format_infix(self, *, compact: bool = False) -> str:
        if not self.factors:
            return "1" if compact or self.coeff == 1 else str(self.coeff)
        if compact:
            body = " ⊗ ".join(token for token, _ in self.factors)
            return body
        parts = [
            f"{token}{_superscript(exp)}" if exp > 1 else token
            for token, exp in self.factors
        ]
        body = " ⊗ ".join(parts)
        if self.coeff == 1:
            return body
        if len(parts) > 1:
            return f"{self.coeff} · ({body})"
        return f"{self.coeff} · {body}"

    def to_dict(self) -> dict[str, object]:
        return {
            "coeff": self.coeff,
            "factors": [{"token": token, "exp": exp} for token, exp in self.factors],
        }


def _format_polynomial_infix(monomials: tuple[Monomial, ...], *, compact: bool = False) -> str:
    if not monomials:
        return "0"
    if compact:
        seen: set[tuple[str, ...]] = set()
        rendered: list[str] = []
        for mon in monomials:
            key = mon.tokens()
            if key in seen:
                continue
            seen.add(key)
            text = mon.format_infix(compact=True)
            if len(key) > 1 and len(monomials) > 1:
                rendered.append(f"({text})")
            else:
                rendered.append(text)
        return " ⊕ ".join(rendered)
    if len(monomials) == 1:
        return monomials[0].format_infix(compact=False)
    parts: list[str] = []
    for mon in monomials:
        text = mon.format_infix(compact=False)
        needs_parens = len(mon.factors) > 1 or mon.coeff > 1
        parts.append(f"({text})" if needs_parens else text)
    return " ⊕ ".join(parts)


def _monomial_sort_key(factors: tuple[tuple[str, int], ...]) -> tuple[int, tuple[tuple[str, int], ...]]:
    return (len(factors), factors)


def _poly_to_expr(monomials: tuple[Monomial, ...]) -> ProvExpr:
    if not monomials:
        return _ZERO
    acc: ProvExpr = _ZERO
    for mon in monomials:
        term: ProvExpr = _ONE
        for token, exp in mon.factors:
            for _ in range(exp):
                term = semiring_mul(term, ProvAtom(token))
        for _ in range(mon.coeff):
            acc = semiring_add(acc, term)
    return acc


@dataclass(frozen=True, slots=True)
class ProvenancePolynomial:
    """Normalized Sum-of-Products element in N[X] with exact and compact views."""

    monomials: tuple[Monomial, ...]
    truncated: bool
    infix_display: str
    compact_infix: str
    npcs_prefix: str
    total_multiplicity: int
    witness_tokens: tuple[str, ...]

    @classmethod
    def from_monomials(
        cls,
        monomials: tuple[Monomial, ...],
        *,
        truncated: bool = False,
        npcs_prefix: str | None = None,
    ) -> ProvenancePolynomial:
        ordered = tuple(sorted(monomials, key=lambda m: _monomial_sort_key(m.factors)))
        tokens = tuple(sorted({tok for m in ordered for tok in m.tokens()}))
        prefix = npcs_prefix if npcs_prefix is not None else to_npcs_prefix(_poly_to_expr(ordered))
        return cls(
            monomials=ordered,
            truncated=truncated,
            infix_display=_format_polynomial_infix(ordered, compact=False),
            compact_infix=_format_polynomial_infix(ordered, compact=True),
            npcs_prefix=prefix,
            total_multiplicity=sum(m.coeff for m in ordered),
            witness_tokens=tokens,
        )

    @classmethod
    def zero(cls) -> ProvenancePolynomial:
        return cls.from_monomials((), npcs_prefix="0")

    @classmethod
    def one(cls) -> ProvenancePolynomial:
        return cls.from_monomials((Monomial(factors=(), coeff=1),), npcs_prefix="1")

    @classmethod
    def atom(cls, token: str) -> ProvenancePolynomial:
        ProvAtom(token)
        return cls.from_monomials((Monomial(factors=((token, 1),), coeff=1),), npcs_prefix=token)

    def add(self, other: ProvenancePolynomial, *, max_terms: int = 512) -> ProvenancePolynomial:
        acc: dict[tuple[tuple[str, int], ...], int] = {m.factors: m.coeff for m in self.monomials}
        truncated = self.truncated or other.truncated
        for mon in other.monomials:
            if mon.factors in acc:
                acc[mon.factors] += mon.coeff
            elif len(acc) < max_terms:
                acc[mon.factors] = mon.coeff
            else:
                truncated = True
        merged = tuple(
            Monomial(factors=factors, coeff=coeff)
            for factors, coeff in sorted(acc.items(), key=lambda kv: _monomial_sort_key(kv[0]))
        )
        return ProvenancePolynomial.from_monomials(merged, truncated=truncated)

    def mul(self, other: ProvenancePolynomial, *, max_terms: int = 512) -> ProvenancePolynomial:
        if not self.monomials or not other.monomials:
            return ProvenancePolynomial.zero()
        acc: dict[tuple[tuple[str, int], ...], int] = {}
        truncated = self.truncated or other.truncated
        for left in self.monomials:
            for right in other.monomials:
                prod = left.mul(right)
                if prod.factors in acc:
                    acc[prod.factors] += prod.coeff
                elif len(acc) < max_terms:
                    acc[prod.factors] = prod.coeff
                else:
                    truncated = True
        merged = tuple(
            Monomial(factors=factors, coeff=coeff)
            for factors, coeff in sorted(acc.items(), key=lambda kv: _monomial_sort_key(kv[0]))
        )
        return ProvenancePolynomial.from_monomials(merged, truncated=truncated)


def to_npcs_prefix(expr: ProvExpr) -> str:
    """Serialize a ProvExpr to canonical NPCS prefix notation, e.g. (+ (* o1 o2) o3)."""
    if isinstance(expr, ProvZero):
        return "0"
    if isinstance(expr, ProvOne):
        return "1"
    if isinstance(expr, ProvAtom):
        return expr.token
    if isinstance(expr, ProvAdd):
        inner = " ".join(to_npcs_prefix(t) for t in expr.terms)
        return f"(+ {inner})"
    if isinstance(expr, ProvMul):
        inner = " ".join(to_npcs_prefix(f) for f in expr.factors)
        return f"(* {inner})"
    raise TypeError(f"Unsupported ProvExpr node: {type(expr).__name__}")


def expand_to_polynomial(expr: ProvExpr, *, max_terms: int = 512) -> ProvenancePolynomial:
    """Expand any ProvExpr to a canonical Sum-of-Products ProvenancePolynomial in N[X]."""
    if max_terms < 1:
        raise ValueError("max_terms must be >= 1")
    truncated = False

    def _expand(node: ProvExpr) -> dict[tuple[tuple[str, int], ...], int]:
        nonlocal truncated
        if isinstance(node, ProvZero):
            return {}
        if isinstance(node, ProvOne):
            return {(): 1}
        if isinstance(node, ProvAtom):
            return {((node.token, 1),): 1}
        if isinstance(node, ProvAdd):
            acc: dict[tuple[tuple[str, int], ...], int] = {}
            for child in node.terms:
                child_map = _expand(child)
                for factors, coeff in child_map.items():
                    if factors in acc:
                        acc[factors] += coeff
                    elif len(acc) < max_terms:
                        acc[factors] = coeff
                    else:
                        truncated = True
            return acc
        if isinstance(node, ProvMul):
            acc: dict[tuple[tuple[str, int], ...], int] = {(): 1}
            for child in node.factors:
                if not acc:
                    return {}
                child_map = _expand(child)
                if not child_map:
                    return {}
                nxt: dict[tuple[tuple[str, int], ...], int] = {}
                for f_left, c_left in acc.items():
                    for f_right, c_right in child_map.items():
                        merged_d: dict[str, int] = dict(f_left)
                        for tok, exp in f_right:
                            merged_d[tok] = merged_d.get(tok, 0) + exp
                        merged_key = tuple(sorted(merged_d.items()))
                        prod_coeff = c_left * c_right
                        if merged_key in nxt:
                            nxt[merged_key] += prod_coeff
                        elif len(nxt) < max_terms:
                            nxt[merged_key] = prod_coeff
                        else:
                            truncated = True
                acc = nxt
            return acc
        raise TypeError(f"Unsupported ProvExpr node: {type(node).__name__}")

    sop = _expand(expr)
    monomials = tuple(
        Monomial(factors=factors, coeff=coeff)
        for factors, coeff in sorted(sop.items(), key=lambda kv: _monomial_sort_key(kv[0]))
    )
    return ProvenancePolynomial.from_monomials(
        monomials,
        truncated=truncated,
        npcs_prefix=to_npcs_prefix(expr),
    )


_NPCS_TOKEN_RE = re.compile(
    r"\s*(?:(?P<lparen>\()|(?P<rparen>\))|(?P<comma>,)|(?P<op>[+*⊕⊗])|(?P<int>\d+)|(?P<ident>[A-Za-z_][A-Za-z0-9_:\-]*))"
)


def _tokenize_npcs(raw: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    length = len(raw)
    while pos < length:
        if raw[pos].isspace():
            pos += 1
            continue
        match = _NPCS_TOKEN_RE.match(raw, pos)
        if not match or match.end() == pos:
            snippet = raw[pos : pos + 16]
            raise ValueError(f"Unexpected token in provenance expression near {snippet!r}")
        kind = match.lastgroup or ""
        tokens.append((kind, match.group(kind)))
        pos = match.end()
    return tokens


def _scalar_expr(value: int) -> ProvExpr:
    if value == 0:
        return _ZERO
    if value == 1:
        return _ONE
    if value > MAX_SCALAR_EXPANSION:
        raise ValueError(f"Scalar coefficient {value} exceeds limit {MAX_SCALAR_EXPANSION}")
    return ProvAdd((_ONE,) * value)


def parse_npcs_prefix(raw: str) -> ProvExpr:
    """Parse NPCS ASCII prefix `(+ (* o1 o2) o3)` or SparqlProv Unicode `(⊕ (⊗ o1 o2) o3)` / `⊕((⊗ o1, o2,))`."""
    if not raw or not raw.strip():
        raise ValueError("Provenance expression cannot be empty")
    tokens = _tokenize_npcs(raw)
    if not tokens:
        raise ValueError("Provenance expression cannot be empty")
    idx = 0

    def peek() -> tuple[str, str] | None:
        return tokens[idx] if idx < len(tokens) else None

    def consume() -> tuple[str, str]:
        nonlocal idx
        tok = tokens[idx]
        idx += 1
        return tok

    def fold_op(op: str, args: list[ProvExpr]) -> ProvExpr:
        if not args:
            raise ValueError(f"Operator {op!r} requires at least one operand")
        if op in ("+", "⊕"):
            acc: ProvExpr = _ZERO
            for arg in args:
                acc = semiring_add(acc, arg)
            return acc
        if op in ("*", "⊗"):
            acc = _ONE
            for arg in args:
                acc = semiring_mul(acc, arg)
            return acc
        raise ValueError(f"Unknown operator {op!r}")

    def parse_arg_list(op: str, depth: int) -> ProvExpr:
        args: list[ProvExpr] = []
        while True:
            nxt = peek()
            if nxt is None:
                raise ValueError("Unclosed '(' in provenance expression")
            if nxt[0] == "rparen":
                consume()
                break
            if nxt[0] == "comma":
                consume()
                continue
            args.append(parse_expr(depth + 1))
            if peek() and peek()[0] == "comma":
                consume()
        return fold_op(op, args)

    def parse_expr(depth: int) -> ProvExpr:
        if depth > MAX_PARSE_DEPTH:
            raise ValueError("Provenance expression nesting depth exceeded")
        tok = peek()
        if tok is None:
            raise ValueError("Unexpected end of provenance expression")
        kind, val = consume()
        if kind == "int":
            return _scalar_expr(int(val))
        if kind == "ident":
            return ProvAtom(val)
        if kind == "op":
            # SparqlProv function-call notation: ⊕(a, b) or ⊕((⊗ o1, o2,))
            nxt = peek()
            if nxt is None or nxt[0] != "lparen":
                raise ValueError(f"Expected '(' after prefix operator {val!r}")
            consume()
            return parse_arg_list(val, depth)
        if kind == "lparen":
            nxt = peek()
            if nxt is None:
                raise ValueError("Unclosed '(' in provenance expression")
            if nxt[0] == "op":
                _, op = consume()
                return parse_arg_list(op, depth)
            # Parenthesized single expression or tuple wrapper used in SparqlProv e.g. ⊕((⊗ o1, o2,))
            inner = parse_expr(depth + 1)
            while peek() and peek()[0] == "comma":
                consume()
            close = peek()
            if close is None or close[0] != "rparen":
                raise ValueError("Expected closing ')' in provenance expression")
            consume()
            return inner
        raise ValueError(f"Unexpected token {val!r} in provenance expression")

    expr = parse_expr(0)
    if idx != len(tokens):
        raise ValueError(f"Unexpected trailing token {tokens[idx][1]!r}")
    return expr
