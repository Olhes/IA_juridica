"""
Ingesta del léxico quechua ancashino (Sihuas + Chiquián) a JSON.

Lee los Excels paralelos (hojas de pares `Oración_Quechua|Oración_Español` y
hojas `Etiquetado` con entidades) y emite `backend/docs/voice/ancash_lexicon.json`:

  {"meta": {...}, "entries": [{id, qu, es, variedad}],
   "variant_index": {es_normalizado: [formas_quechua...]},
   "entities": [{qu, es, tags, variedad}]}

Uso (desde backend/):
    python scripts/ingest_ancash_lexicon.py
    python scripts/ingest_ancash_lexicon.py --corpus-dir <dir> --out <json>

La canonicalización usa la MISMA `normalize_ancash()` del módulo de voz para
que las claves del JSON coincidan con la caché TTS y el normalizador.
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from modules.voice.services.text_normalizer_ancash import normalize_ancash  # noqa: E402

DEFAULT_CORPUS = BACKEND_DIR / "docs" / "voice" / "corpus"
DEFAULT_OUT = BACKEND_DIR / "docs" / "voice" / "ancash_lexicon.json"

SOURCES = [
    ("QuechuaSihuas.xlsx", "sihuas"),
    ("QuechuaChiquian.xlsx", "chiquian"),
]


def _find_header(rows: list) -> int | None:
    for i, row in enumerate(rows[:10]):
        cells = [(c or "") for c in row]
        joined = " ".join(str(c).casefold() for c in cells)
        if "quechua" in joined and "espa" in joined:
            return i
    return None


def _col_index(header: list, *needles: str) -> int | None:
    for i, cell in enumerate(header):
        name = str(cell or "").casefold()
        if all(n in name for n in needles):
            return i
    return None


def parse_pairs(wb, variedad: str) -> tuple[list, dict]:
    """Extrae pares (qu, es) de la hoja de oraciones. Retorna (entries, stats)."""
    entries, stats = [], {"rows": 0, "empty": 0, "dups": 0}
    seen = set()
    sheet = next((s for s in wb.sheetnames if "etiquetado" not in s.casefold()), wb.sheetnames[0])
    ws = wb[sheet]
    rows = [r for r in ws.iter_rows(values_only=True)]
    hi = _find_header(rows)
    if hi is None:
        return entries, stats
    header = rows[hi]
    qi = _col_index(header, "quechua")
    ei = _col_index(header, "espa")
    vi = _col_index(header, "variedad")
    ni = _col_index(header, "n")
    if qi is None or ei is None:
        return entries, stats
    for row in rows[hi + 1:]:
        stats["rows"] += 1
        qu = str(row[qi]).strip() if qi < len(row) and row[qi] else ""
        es = str(row[ei]).strip() if ei < len(row) and row[ei] else ""
        if not qu or not es:
            stats["empty"] += 1
            continue
        key = normalize_ancash(qu)
        if key in seen:
            stats["dups"] += 1
            continue
        seen.add(key)
        n = str(row[ni]).strip() if ni is not None and ni < len(row) and row[ni] else str(len(entries) + 1)
        var = str(row[vi]).strip().casefold() if vi is not None and vi < len(row) and row[vi] else variedad
        entries.append({"id": f"{var}:{n}", "qu": qu, "es": es, "variedad": var})
    return entries, stats


def parse_entities(wb, variedad: str) -> list:
    """Extrae entidades de la hoja `Etiquetado`: qu + tags tipo 'Lima - ciudad'.

    Las hojas Etiquetado de ambos Excels se solapan (~46 oraciones únicas):
    se deduplica por (oración normalizada, tags) acumulando variedades.
    """
    by_key: dict = {}
    sheet = next((s for s in wb.sheetnames if "etiquetado" in s.casefold()), None)
    if sheet is None:
        return []
    for row in wb[sheet].iter_rows(values_only=True):
        cells = [(str(c).strip() if c not in (None, "") else "") for c in row]
        if len(cells) < 5 or not cells[2]:
            continue
        tags = [c for c in cells[4:] if c and " - " in c]
        if not tags:
            continue
        key = (normalize_ancash(cells[2]), tuple(tags))
        if key in by_key:
            if variedad not in by_key[key]["variedades"]:
                by_key[key]["variedades"].append(variedad)
        else:
            by_key[key] = {"qu": cells[2], "es": cells[3] or "", "tags": tags, "variedades": [variedad]}
    return list(by_key.values())


def build_lexicon(corpus_dir: Path) -> dict:
    import openpyxl

    entries, entities, stats = [], [], {}
    for fname, variedad in SOURCES:
        path = corpus_dir / fname
        if not path.exists():
            stats[variedad] = {"missing": str(path)}
            continue
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        pairs, st = parse_pairs(wb, variedad)
        entries.extend(pairs)
        stats[variedad] = {**st, "pairs": len(pairs)}
        for e in parse_entities(wb, variedad):  # dedup global entre archivos
            key = (normalize_ancash(e["qu"]), tuple(e["tags"]))
            dup = next((x for x in entities if (normalize_ancash(x["qu"]), tuple(x["tags"])) == key), None)
            if dup:
                for v in e["variedades"]:
                    if v not in dup["variedades"]:
                        dup["variedades"].append(v)
                stats[variedad]["ent_dups"] = stats[variedad].get("ent_dups", 0) + 1
            else:
                entities.append(e)
        stats[variedad]["entities"] = len(entities)

    variant_index: dict[str, list] = {}
    for e in entries:
        variant_index.setdefault(normalize_ancash(e["es"]), set()).add(e["qu"])
    variant_index = {k: sorted(v) for k, v in variant_index.items()}

    return {
        "meta": {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sources": [f for f, _ in SOURCES],
            "varieties": ["sihuas", "chiquian"],
            "counts": {"pairs": len(entries), "entities": len(entities)},
            "stats": stats,
        },
        "entries": entries,
        "variant_index": variant_index,
        "entities": entities,
    }


def main(corpus_dir: Path = DEFAULT_CORPUS, out: Path = DEFAULT_OUT) -> dict:
    lex = build_lexicon(corpus_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lex, ensure_ascii=False, indent=1), encoding="utf-8")
    m = lex["meta"]
    print(f"pares: {m['counts']['pairs']} | entidades: {m['counts']['entities']} -> {out}")
    for var, st in m["stats"].items():
        print(f"  {var}: {st}")
    multi = sum(1 for v in lex["variant_index"].values() if len(v) > 1)
    print(f"glosas con >1 variante quechua: {multi}")
    return lex


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    main(args.corpus_dir, args.out)
