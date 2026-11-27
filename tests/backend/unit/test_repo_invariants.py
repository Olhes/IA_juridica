"""Repository-wide structural invariants enforced in CI for recurring mistake classes."""

from __future__ import annotations

import gzip
from pathlib import Path
import re

from scripts import bootstrap_sat_corpus as bootstrap_mod


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SNAPSHOT = BACKEND_DIR / "docs" / "sat_graph.surql.gz"

MAX_SNAPSHOT_GZ_BYTES = 12 * 1024 * 1024
MAX_SNAPSHOT_RAW_BYTES = 50 * 1024 * 1024
MAX_INSERT_LINE_BYTES = 600_000
MAX_SINGLE_OBJECT_LINE_BYTES = 1_500_000


def test_sat_snapshot_is_compact_valid_and_free_of_superseded_bloat():
    """Prevent bloated, corrupted, or uncompacted sat_graph.surql.gz snapshots from landing."""
    assert SNAPSHOT.is_file(), f"Missing SAT snapshot at {SNAPSHOT}"
    gz_size = SNAPSHOT.stat().st_size
    assert gz_size <= MAX_SNAPSHOT_GZ_BYTES, (
        f"{SNAPSHOT.name} is {gz_size / (1024 * 1024):.2f} MB gzipped "
        f"(cap {MAX_SNAPSHOT_GZ_BYTES // (1024 * 1024)} MB). "
        "Run `python backend/scripts/bootstrap_sat_corpus.py --compact`."
    )

    expected = bootstrap_mod._parse_expected_rows(SNAPSHOT)
    raw_bytes = 0
    emitted_objects = 0
    cur_table: str | None = None
    active_revisions = 0

    with gzip.open(SNAPSHOT, "rt", encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, start=1):
            line_bytes = len(line.encode("utf-8"))
            raw_bytes += line_bytes
            stripped = line.strip()
            match = bootstrap_mod._SECTION_TABLE_RE.match(stripped)
            if match:
                cur_table = match.group(1)
                continue
            if not stripped.startswith("INSERT "):
                continue
            assert "INSERT [ INSERT [" not in stripped, (
                f"Nested INSERT wrapper at {SNAPSHOT.name}:{lineno}. "
                "Use bootstrap_sat_corpus._extract_insert_objects and _pack_insert_objects."
            )
            objs = bootstrap_mod._extract_insert_objects(stripped)
            assert objs, f"Unparseable INSERT statement at {SNAPSHOT.name}:{lineno}."
            line_cap = MAX_SINGLE_OBJECT_LINE_BYTES if len(objs) == 1 else MAX_INSERT_LINE_BYTES
            assert line_bytes <= line_cap, (
                f"Line {lineno} in {SNAPSHOT.name} ({len(objs)} objs) is {line_bytes} bytes "
                f"(cap {line_cap}). Run `bootstrap_sat_corpus.py --compact`."
            )
            emitted_objects += len(objs)
            if cur_table == "sat_nodes":
                for obj in objs:
                    kind = bootstrap_mod._extract_surql_string(obj, "kind")
                    if kind == "DocumentaryRevision":
                        active_revisions += 1
                        payload = bootstrap_mod._extract_surql_payload(obj)
                        assert not payload.get("editorial_superseded_by"), (
                            "Superseded DocumentaryRevision found in snapshot. Run `--compact`."
                        )
                    elif kind == "CTV":
                        payload = bootstrap_mod._extract_surql_payload(obj)
                        assert not payload.get("editorial_superseded_by"), (
                            "Superseded CTV found in snapshot. Run `--compact`."
                        )

    assert raw_bytes <= MAX_SNAPSHOT_RAW_BYTES, (
        f"{SNAPSHOT.name} is {raw_bytes / (1024 * 1024):.2f} MB uncompressed "
        f"(cap {MAX_SNAPSHOT_RAW_BYTES // (1024 * 1024)} MB). Run `--compact`."
    )
    assert active_revisions >= 1, "Snapshot must retain active DocumentaryRevision headers for readiness checks."
    assert emitted_objects == sum(expected.values()), (
        f"EXPECTED_ROWS sum ({sum(expected.values())}) != emitted objects ({emitted_objects})."
    )


def test_no_raw_cohere_thinking_disabled_outside_cohere_chat():
    """Cohere command-a-plus leaks reasoning into text when thinking.type == 'disabled'."""
    pattern = re.compile(r"""["']type["']\s*:\s*["']disabled["']""")
    offenders: list[str] = []
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        if path.name == "cohere_chat.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "thinking" in text and pattern.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"Direct Cohere thinking disabled dict found in {offenders}. "
        "Use `services.cohere_chat.default_thinking_option()` instead."
    )


def test_surreal_chat_snapshots_always_tag_chat_revision():
    """All SurrealSATGraphStore chat_*_snapshot methods must return chat_revision for zero-copy retrieval."""
    surreal_src = (BACKEND_DIR / "ingestion" / "sat_graph" / "surreal.py").read_text(encoding="utf-8")
    for method in ("chat_snapshot", "chat_heading_snapshot", "chat_article_snapshot"):
        start = surreal_src.index(f"def {method}(")
        next_def = surreal_src.find("\n    def ", start + 1)
        body = surreal_src[start:] if next_def == -1 else surreal_src[start:next_def]
        assert '"chat_revision": revision' in body or "'chat_revision': revision" in body, (
            f"SurrealSATGraphStore.{method} must include 'chat_revision': revision "
            "so SATChatRetriever skips deepcopy and JSON fingerprinting."
        )
