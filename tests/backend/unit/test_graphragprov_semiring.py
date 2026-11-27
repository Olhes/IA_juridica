"""Unit tests for the N[X] how-provenance semiring and NPCS prefix codec."""
from __future__ import annotations

import pytest

from services.graphragprov.semiring import (
    Monomial,
    ProvAdd,
    ProvAtom,
    ProvMul,
    ProvOne,
    ProvZero,
    ProvenancePolynomial,
    atom,
    expand_to_polynomial,
    one,
    parse_npcs_prefix,
    semiring_add,
    semiring_mul,
    to_npcs_prefix,
    zero,
)


def test_semiring_axioms_commutativity_associativity_distributivity_and_identities():
    a, b, c = atom("occ_000000000001"), atom("occ_000000000002"), atom("occ_000000000003")

    # Additive and multiplicative identities and annihilator
    assert expand_to_polynomial(semiring_add(a, zero())) == expand_to_polynomial(a)
    assert expand_to_polynomial(semiring_add(zero(), a)) == expand_to_polynomial(a)
    assert expand_to_polynomial(semiring_mul(a, one())) == expand_to_polynomial(a)
    assert expand_to_polynomial(semiring_mul(one(), a)) == expand_to_polynomial(a)
    assert expand_to_polynomial(semiring_mul(a, zero())).monomials == ()
    assert expand_to_polynomial(semiring_mul(zero(), a)).infix_display == "0"

    # Commutativity of + and *
    assert (
        expand_to_polynomial(semiring_add(a, b)).monomials
        == expand_to_polynomial(semiring_add(b, a)).monomials
    )
    assert (
        expand_to_polynomial(semiring_mul(a, b)).monomials
        == expand_to_polynomial(semiring_mul(b, a)).monomials
    )

    # Associativity of + and *
    assert (
        expand_to_polynomial(semiring_add(semiring_add(a, b), c)).monomials
        == expand_to_polynomial(semiring_add(a, semiring_add(b, c))).monomials
    )
    assert (
        expand_to_polynomial(semiring_mul(semiring_mul(a, b), c)).monomials
        == expand_to_polynomial(semiring_mul(a, semiring_mul(b, c))).monomials
    )

    # Distributivity: a * (b + c) == (a * b) + (a * c)
    lhs = expand_to_polynomial(semiring_mul(a, semiring_add(b, c)))
    rhs = expand_to_polynomial(semiring_add(semiring_mul(a, b), semiring_mul(a, c)))
    assert lhs.monomials == rhs.monomials
    assert lhs.witness_tokens == ("occ_000000000001", "occ_000000000002", "occ_000000000003")


def test_semiring_preserves_multiplicity_and_formats_exact_and_compact_views():
    o1 = atom("o1")
    o2 = atom("o2")

    # o1 + o1 = 2 * o1
    doubled = expand_to_polynomial(semiring_add(o1, o1))
    assert doubled.monomials == (Monomial(factors=(("o1", 1),), coeff=2),)
    assert doubled.total_multiplicity == 2
    assert doubled.infix_display == "2 · o1"
    assert doubled.compact_infix == "o1"

    # o1 * o1 = o1^2
    squared = expand_to_polynomial(semiring_mul(o1, o1))
    assert squared.monomials == (Monomial(factors=(("o1", 2),), coeff=1),)
    assert squared.infix_display == "o1²"
    assert squared.compact_infix == "o1"

    # Mixed expression: (o1 * o2) + o1 + o1
    mixed = expand_to_polynomial(semiring_add(semiring_mul(o1, o2), semiring_add(o1, o1)))
    assert mixed.total_multiplicity == 3
    assert "2 · o1" in mixed.infix_display
    assert "o1 ⊗ o2" in mixed.infix_display
    assert "2 ·" not in mixed.compact_infix
    assert "o1" in mixed.compact_infix and "o1 ⊗ o2" in mixed.compact_infix


def test_provenance_polynomial_direct_algebra():
    p1 = ProvenancePolynomial.atom("o1")
    p2 = ProvenancePolynomial.atom("o2")
    prod = p1.mul(p2)
    assert prod.infix_display == "o1 ⊗ o2"
    summed = prod.add(prod)
    assert summed.monomials == (Monomial(factors=(("o1", 1), ("o2", 1)), coeff=2),)
    assert summed.total_multiplicity == 2


@pytest.mark.parametrize(
    "raw,expected_monomials",
    [
        ("0", ()),
        ("1", (Monomial(factors=(), coeff=1),)),
        ("o1", (Monomial(factors=(("o1", 1),), coeff=1),)),
        (
            "(+ (* o1 o2) o3)",
            (
                Monomial(factors=(("o3", 1),), coeff=1),
                Monomial(factors=(("o1", 1), ("o2", 1)), coeff=1),
            ),
        ),
        (
            "(⊕ (⊗ o1 o2) o3)",
            (
                Monomial(factors=(("o3", 1),), coeff=1),
                Monomial(factors=(("o1", 1), ("o2", 1)), coeff=1),
            ),
        ),
        (
            "⊕((⊗ o1, o2,), o3)",
            (
                Monomial(factors=(("o3", 1),), coeff=1),
                Monomial(factors=(("o1", 1), ("o2", 1)), coeff=1),
            ),
        ),
        (
            "⊕(⊗(o1, o2), o1, o1)",
            (
                Monomial(factors=(("o1", 1),), coeff=2),
                Monomial(factors=(("o1", 1), ("o2", 1)), coeff=1),
            ),
        ),
        (
            "(* 2 o1)",
            (Monomial(factors=(("o1", 1),), coeff=2),),
        ),
    ],
)
def test_npcs_and_sparqlprov_prefix_parser_round_trip(raw, expected_monomials):
    expr = parse_npcs_prefix(raw)
    poly = expand_to_polynomial(expr)
    assert poly.monomials == expected_monomials

    # Serializing to canonical NPCS prefix and reparsing preserves the exact polynomial.
    reparsed = expand_to_polynomial(parse_npcs_prefix(to_npcs_prefix(expr)))
    assert reparsed.monomials == poly.monomials


def test_expand_to_polynomial_respects_max_terms_truncation_guard():
    # (a0 + b0) * (a1 + b1) * ... * (a5 + b5) produces 64 monomials.
    expr = one()
    for i in range(6):
        expr = semiring_mul(expr, semiring_add(atom(f"a{i}"), atom(f"b{i}")))
    poly = expand_to_polynomial(expr, max_terms=10)
    assert poly.truncated is True
    assert len(poly.monomials) == 10
    assert poly.npcs_prefix.startswith("(* ")


@pytest.mark.parametrize("bad_input", ["", "   ", "(+ o1", "(+ o1 o2))", "(+ )", "o1 o2", "(* 99999 o1)"])
def test_npcs_parser_rejects_malformed_inputs(bad_input):
    with pytest.raises(ValueError):
        parse_npcs_prefix(bad_input)
