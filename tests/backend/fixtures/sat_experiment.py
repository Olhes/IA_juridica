"""Corpus artificial congelable: NO usar como fuente jurídica ni base de producción."""

from hashlib import sha256
import json
from pathlib import Path
import sys


def dataset():
    nodes, edges = [], []
    resources = ("pe:fixture:protection", "pe:fixture:family")
    for rid, title in zip(
        resources, ("Norma FICTICIA de protección", "Norma FICTICIA de alimentos")
    ):
        nodes.append(
            {
                "id": rid,
                "type": "Resource",
                "kind": "norm",
                "title": title,
                "url": "https://example.invalid/fixture",
            }
        )

    def version(resource, component, label, text, start, end=None):
        wid = f"work:{resource}/{component}"
        if not any(n["id"] == wid for n in nodes):
            nodes.append(
                {
                    "id": wid,
                    "type": "Work",
                    "resource_id": resource,
                    "component": component,
                    "label": label,
                }
            )
        vid = f"ctv:{component}:{start}"
        tid = "text:" + vid
        audit = {
            "evidence_id": "synthetic-evidence",
            "review_id": "engineering-fixture-not-lawyer",
            "source_url": "https://example.invalid/fixture",
        }
        nodes.append(
            {
                "id": vid,
                "type": "CTV",
                "work_id": wid,
                "scope": "PE",
                "valid_from": start,
                "valid_to": end,
                "checked_through": "2026-10-10",
                "provenance_state": "reviewed",
                **audit,
            }
        )
        nodes.append(
            {
                "id": tid,
                "type": "CLV",
                "language": "es",
                "text": text,
                "start": 0,
                "end": len(text),
                "text_sha256": sha256(text.encode()).hexdigest(),
                **audit,
            }
        )
        edges.append({"source": vid, "type": "has_text", "target": tid})
        return vid

    r1, r2 = resources
    old_root = version(
        r1,
        "chapter",
        "Protección familiar",
        "Capítulo ficticio de protección familiar.",
        "2020-01-01",
        "2025-01-01",
    )
    new_root = version(
        r1,
        "chapter",
        "Protección familiar",
        "Capítulo ficticio de protección familiar.",
        "2025-01-01",
    )
    old = version(
        r1,
        "protection",
        "Solicitud de medidas",
        "Regla inventada: solicitar medida de protección en oficina ámbar.",
        "2020-01-01",
        "2025-01-01",
    )
    new = version(
        r1,
        "protection",
        "Solicitud de medidas",
        "Regla inventada: solicitar medida de protección en oficina azul.",
        "2025-01-01",
    )
    proof = version(
        r1,
        "proof",
        "Documentos para la solicitud",
        "Regla inventada: adjuntar constancia de identidad para la solicitud.",
        "2020-01-01",
    )
    pay = version(
        r2,
        "payment",
        "Constancias de alimentos",
        "Regla inventada: acreditar pagos de alimentos mediante constancia bancaria.",
        "2020-01-01",
    )
    debt = version(
        r2,
        "debt",
        "Registro de deuda",
        "Regla inventada: solicitar inscripción de deuda con resolución y liquidación.",
        "2020-01-01",
    )
    visit = version(
        r2,
        "visits",
        "Visitas",
        "Regla inventada: coordinar visitas familiares en un horario acordado.",
        "2020-01-01",
    )
    for parent, children in ((old_root, [old, proof]), (new_root, [new, proof])):
        for child in children:
            edges.append(
                {"source": parent, "type": "contains_version", "target": child}
            )

    def case(
        identity,
        query,
        expected,
        *,
        when="2025-01-01",
        resource=None,
        component=None,
        stratum="single",
        split="development",
    ):
        plan = {"query": query, "as_of": when}
        if resource:
            plan["resource_ids"] = [resource]
        if component:
            plan["component"] = component
        return {
            "id": identity,
            "plan": plan,
            "expected_version_ids": expected,
            "answerable": bool(expected),
            "stratum": stratum,
            "split": split,
        }

    cases = [
        case(
            "old-protection",
            "solicitar medida de protección",
            [old],
            when="2024-12-31",
            resource=r1,
        ),
        case("new-protection", "solicitar medida de protección", [new], resource=r1),
        case(
            "boundary-old",
            "oficina ámbar protección",
            [old],
            when="2024-12-31",
            resource=r1,
            component="protection",
            stratum="boundary",
        ),
        case(
            "boundary-new",
            "oficina azul protección",
            [new],
            resource=r1,
            component="protection",
            stratum="boundary",
        ),
        case(
            "payment",
            "acreditar pagos alimentos constancia bancaria",
            [pay],
            resource=r2,
        ),
        case("debt", "inscripción deuda resolución liquidación", [debt], resource=r2),
        case(
            "multi-evidence",
            "solicitud protección constancia identidad",
            [new, proof],
            resource=r1,
            stratum="multi",
        ),
        case(
            "cross-document",
            "medida protección y pagos alimentos",
            [new, pay],
            stratum="multi",
        ),
        case(
            "outside-coverage",
            "medida protección",
            [],
            when="2026-10-11",
            stratum="coverage",
        ),
        case(
            "before-enactment",
            "pagos alimentos",
            [],
            when="2019-12-31",
            stratum="boundary",
        ),
        case(
            "absent-instrument",
            "medida protección",
            [],
            resource="pe:fixture:absent",
            stratum="hard_filter",
        ),
        case(
            "absent-component",
            "medida protección",
            [],
            resource=r1,
            component="absent",
            stratum="hard_filter",
        ),
        case(
            "heldout-payment",
            "constancia para acreditar el pago",
            [pay],
            resource=r2,
            split="heldout",
        ),
        case(
            "heldout-visits",
            "horario de visitas familiares",
            [visit],
            resource=r2,
            split="heldout",
        ),
    ]
    return {
        "schema_version": 1,
        "kind": "synthetic_engineering",
        "revision": "sat-mechanisms-v1",
        "warning": "Textos, fechas y revisiones inventados. No certifica derecho peruano ni calidad de producción.",
        "snapshot": {"nodes": nodes, "edges": edges},
        "cases": cases,
        "config": {
            "top_k": 3,
            "candidates": 20,
            "chunk_chars": 1000,
            "context_bytes": 16000,
        },
    }


if __name__ == "__main__":
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(dataset(), stream, ensure_ascii=False, indent=2)
