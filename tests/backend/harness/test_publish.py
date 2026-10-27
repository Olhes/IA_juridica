"""Publicación de métricas: solo sistemas reales, solo agregados y avisos honestos."""

import json

import pytest

from evaluation.harness import publish
from services import quality_reports

pytestmark = pytest.mark.harness


def write(results, sha, suite, data):
    folder = results / sha
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{suite}.json").write_text(json.dumps(data), encoding="utf-8")


def metric(value, n=5):
    return {"macro": {"value": value, "n": n}, "micro": {"value": value}, "n": n}


def test_synthetic_baselines_are_published_as_not_measured_never_as_quality(tmp_path):
    write(tmp_path, "abc", "translation", {"meta": {"answer_source": "identity_baseline"}, "metrics": {"chrf++": metric(0.09)}})
    write(tmp_path, "abc", "stream", {"meta": {"answer_source": "stub_pipeline"}, "n_streams": 5, "valid_stream_rate": 1.0})
    published = publish.build_published(tmp_path, "abc")
    for suite in ("translation", "stream"):
        assert published["suites"][suite]["measured"] is False and "metrics" not in published["suites"][suite]
    assert "línea base" in published["suites"]["translation"]["reason"] and "simulado" in published["suites"]["stream"]["reason"]
    assert published["suites"]["legal_qa"] == {"measured": False, "reason": "Aún no se ejecutó esta evaluación."}


def test_real_systems_publish_aggregates_without_any_case_text(tmp_path):
    secret = "TEXTO PRIVADO DE UNA CONSULTA"
    write(tmp_path, "abc", "legal_qa", {
        "meta": {"answer_source": "cassette", "judge": {"name": "none"}, "created_at": "2026-10-22T00:00:00+00:00", "dirty": True,
                 "prompt_digest": "d" * 64, "corpus_revision": "r"},
        "n_cases": 2, "n_errors": 0, "gold": {"adjudicated": 0, "status": {"candidate": 2}},
        "metrics": {"legal_factuality": metric(0.5), "fact_recall": metric(0.6)}, "calibration": {"n": 2, "ece": 0.3, "brier": 0.2, "bins": [1]},
        "cases": [{"id": secret}], "answers": [{"answer": {"text": secret}}],
    })
    write(tmp_path, "abc", "retrieval", {
        "meta": {"answer_source": "offline_engine"}, "source": "offline", "n_cases": 3,
        "main": {"lexical": {"evidence_recall@5": metric(0.6), "mrr": metric(0.5)}, "lightrag_naive": {"evidence_recall@5": metric(None, 0)}},
        "index_audit": {"indexed_chunks": 10, "segment_coverage": 0.8, "gold_segments": 5, "gold_segments_covered": 4, "gold_segments_missing": [secret]},
        "corpus_quality": {"spaced_documents": ["a", "b"]},
    })
    published = publish.build_published(tmp_path, "abc")
    assert published["dirty"] is True and published["status"] == "preliminar" and published["sha"] == "abc"
    qa = published["suites"]["legal_qa"]
    assert qa["measured"] is True and qa["metrics"]["legal_factuality"] == {"macro": 0.5, "micro": 0.5, "n": 5} and qa["gold"]["adjudicated"] == 0
    retrieval = published["suites"]["retrieval"]
    assert set(retrieval["systems"]) == {"lexical"} and "sin LightRAG" in retrieval["note"] and retrieval["spaced_ocr_documents"] == 2
    assert secret not in json.dumps(published)
    assert any("candidatos" in notice for notice in published["notices"]) and any("no certifican" in notice for notice in published["notices"])


def test_published_file_round_trips_and_a_missing_file_is_reported_as_unpublished(tmp_path):
    path = publish.write_published({"schema": 1, "status": "preliminar", "suites": {}, "notices": ["ñ"]}, tmp_path / "docs" / "published.json")
    assert quality_reports.load_published(path)["notices"] == ["ñ"]
    assert quality_reports.load_published(tmp_path / "no-existe.json")["status"] == "sin_publicar"
    path.write_text("{ roto", encoding="utf-8")
    assert quality_reports.load_published(path)["status"] == "sin_publicar"


def test_retrieval_publication_explains_the_ndcg_unit_and_version():
    report = {"meta": {"answer_source": "offline_engine"}, "source": "offline",
              "ndcg_definition": "binary_unique_segments_tie_averaged_v1",
              "main": {"lexical": {"ndcg@5": metric(1.0)}}}
    entry = publish.publish_suite("retrieval", report)
    assert "sin LightRAG" in entry["note"]
    assert "segmentos únicos" in entry["note"]
    assert "sin recalcularlos" in entry["note"]
    assert entry["systems"]["lexical"]["ndcg@5"]["macro"] == 1.0


def test_the_checked_in_published_file_is_honest_about_what_was_measured():
    published = quality_reports.load_published()
    assert published["status"] in {"preliminar", "sin_publicar"}
    assert published["notices"] and all(isinstance(n, str) for n in published["notices"])
    for suite, entry in published.get("suites", {}).items():
        assert entry["measured"] in (True, False), suite
        if entry["measured"]:
            assert entry["answer_source"] in publish.REAL_SOURCES, suite
        else:
            assert entry["reason"], suite
    assert "query" not in json.dumps(published) and "answer" not in json.dumps(published).replace("answer_source", "")


def test_latest_comparison_picks_the_newest_report_and_ignores_broken_files(tmp_path):
    older, newer, broken = (tmp_path / "compare" / name for name in ("a..b", "c..d", "e..f"))
    for folder in (older, newer, broken):
        folder.mkdir(parents=True)
    (older / "report.json").write_text(json.dumps({"verdict": {"verdict": "IGUAL"}}), encoding="utf-8")
    (newer / "report.json").write_text(json.dumps({"verdict": {"verdict": "MEJORÓ", "blocking": False, "blocks": []}, "suites": []}), encoding="utf-8")
    import os
    os.utime(older / "report.json", (1, 1))
    (broken / "report.json").write_text("{ roto", encoding="utf-8")
    os.utime(broken / "report.json", (2, 2))
    assert quality_reports.latest_comparison(tmp_path)["verdict"] == "MEJORÓ"
    assert quality_reports.latest_comparison(tmp_path / "vacio") is None
