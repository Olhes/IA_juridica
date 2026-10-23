"""Gold paralelo es→qu, métricas de traducción y suite de traducción (sin proveedores)."""

import json

import pytest

from evaluation.harness import runner, translation_eval
from evaluation.harness.gold import GoldValidationError
from evaluation.harness.metrics import translation as t
from evaluation.harness.translation_eval import Output, evaluate_translation, identity_outputs, language_id_check
from evaluation.harness.translation_gold import (
    TRANSLATION_PATH,
    TranslationPair,
    load_pairs,
    strip_page_noise,
    verify_pair,
)
from evaluation.harness.translation_seed import build_seed

pytestmark = pytest.mark.harness


@pytest.fixture(scope="session")
def pairs():
    return load_pairs()


@pytest.fixture(scope="session")
def by_id(pairs):
    return {p.id: p for p in pairs}


def raw_pair(pair):
    return json.loads(json.dumps(pair.model_dump(mode="json")))


def test_seed_pairs_are_candidates_with_native_review_pending(pairs):
    assert len(pairs) >= 250
    assert {p.status for p in pairs} == {"candidate"} and all(p.reviewers == [] for p in pairs)
    assert {p.kind for p in pairs} == {"sentence", "article", "title", "term"}
    assert {p.variant for p in pairs} == {"cusco-collao", "chanka", "sureno-sin-confirmar"}
    assert {p.split for p in pairs} == {"dev", "holdout"}
    assert all(p.reference_quality == "clean" for p in pairs)


def test_every_pair_is_found_in_its_printed_source(pairs):
    assert [problem for pair in pairs for problem in verify_pair(pair)] == []


def test_checked_in_jsonl_matches_the_seed_definition(pairs):
    """El JSONL se regenera con ``python -m evaluation.harness.translation_seed``; no se edita a mano."""
    built, dropped = build_seed()
    assert sorted(built, key=lambda p: p.id) == sorted(pairs, key=lambda p: p.id)
    assert sum(dropped.values()) > 0  # las filas dudosas se descartan y se cuentan


def test_verification_rejects_invented_text_and_missing_sources(by_id):
    pair = raw_pair(by_id["cc-l1141"])
    assert verify_pair(TranslationPair.model_validate({**pair, "references_qu": ["Una oración quechua inventada por completo"]}))
    assert verify_pair(TranslationPair.model_validate({**pair, "source_es": "Frase en español que no figura en el manual"}))
    assert verify_pair(TranslationPair.model_validate({**pair, "origin": {"file": "no-existe.md", "locator": "x"}}))


def test_pairs_need_two_blind_native_reviewers_to_be_adjudicated(by_id):
    pair = raw_pair(by_id["cc-l1141"])
    reviewers = [
        {"id": r, "role": "hablante_nativo", "variant": "cusco-collao", "blind": True, "verdict": "approve", "reviewed_at": "2026-10-22"}
        for r in ("nativo-1", "nativo-2")
    ]
    assert TranslationPair.model_validate({**pair, "status": "adjudicated", "reviewers": reviewers}).status == "adjudicated"
    for bad in (
        {"status": "adjudicated", "reviewers": reviewers[:1]},
        {"status": "candidate", "reviewers": reviewers},
        {"status": "reviewed", "reviewers": []},
        {"kind": "parrafo"},
        {"variant": "central-inventado"},
        {"references_qu": []},
    ):
        with pytest.raises(ValueError):
            TranslationPair.model_validate({**pair, **bad})


def test_loader_reports_broken_lines_and_duplicates(tmp_path, by_id):
    line = json.dumps(raw_pair(by_id["cc-l1141"]), ensure_ascii=False)
    path = tmp_path / "broken.jsonl"
    path.write_text(f"{line}\n{{ roto\n{line}\n", encoding="utf-8")
    with pytest.raises(GoldValidationError) as error:
        load_pairs(path, verify=False)
    assert any("línea 2" in p for p in error.value.problems) and any("repetidos" in p for p in error.value.problems)


def test_loader_filters_kinds_splits_and_adjudicated(pairs):
    assert {p.kind for p in load_pairs(kinds=["term"])} == {"term"}
    assert {p.split for p in load_pairs(splits=["holdout"])} == {"holdout"}
    assert load_pairs(only_adjudicated=True) == []
    assert TRANSLATION_PATH.exists()


def test_page_noise_is_removed_from_sources():
    assert strip_page_noise("Texto\n- 17 -\n30364 Kamachiy Qillqa\n<!-- image -->\nsigue") == "Texto\nsigue"


def test_chrf_matches_hand_computed_values_and_ignores_whitespace_in_characters():
    assert t.chrf("allin p'unchaw", ["allin p'unchaw"]) == pytest.approx(100.0)
    assert t.chrf("abc", ["xyz"]) == 0.0
    # Caracteres 1-2 coinciden y las palabras no: P = R = 2/3 => F = 66.67.
    assert t.chrf("a b", ["ab"]) == pytest.approx(66.6667, abs=1e-3)
    assert t.chrf("uno dos tres cuatro", ["uno dos tres cinco"]) < 100
    assert t.chrf("uno dos tres", ["uno dos tres cinco", "uno dos tres"]) == pytest.approx(100.0)  # mejor referencia


def test_chrf_rewards_recall_more_than_precision():
    reference = ["kay qillqa allinmi kachkan"]
    short = t.chrf("kay qillqa", reference)
    padded = t.chrf("kay qillqa allinmi kachkan hinallataq huk rimay", reference)
    assert padded > short  # beta=2 pesa más el recall


def test_bleu_and_ter_follow_their_definitions():
    sentence = "Kay qillqa allinmi kachkan chaymi"
    assert t.bleu_from_stats(t.bleu_stats(sentence, sentence)) == pytest.approx(100.0)
    assert t.bleu_from_stats(t.bleu_stats("a b", "a b c d")) == 0.0  # hipótesis más corta que 4 palabras
    partial = t.bleu_from_stats(t.bleu_stats("Kay qillqa allinmi kachkan hinaspa", sentence))
    assert 0 < partial < 100
    assert t.ter("uno dos tres cuatro", ["uno dos tres cuatro"]) == 0.0
    assert t.ter("uno dos tres cuatro", ["uno dos tres cinco"]) == pytest.approx(25.0)
    assert t.ter("uno dos", ["uno dos tres cuatro"]) == pytest.approx(50.0)
    assert t.ter("x y z w", ["uno dos tres cuatro", "x y z w"]) == 0.0


def test_corpus_bleu_sums_statistics_instead_of_averaging_sentences():
    one = t.bleu_stats("Kay qillqa allinmi kachkan", "Kay qillqa allinmi kachkan")
    two = t.bleu_stats("Manan qullqita quwanchu", "Manan qullqita quwanmanchu")
    merged = t.merge_bleu_stats([one, two])
    assert merged["hyp_len"] == one["hyp_len"] + two["hyp_len"]
    assert 0 < t.bleu_from_stats(merged) < 100


def test_contract_signals_references_placeholders_language_copy_and_coverage():
    source = "Según el artículo 475 y la Ley 30364, la pensión cubre salud [1] https://x.pe/a."
    assert t.references_kept(source, "Artículo 475, Ley 30364 [1] https://x.pe/a. Kay qillqa").value == 1.0
    lost = t.references_kept(source, "Kay qillqa allinmi, Ley 30364")
    assert lost.value < 1.0 and lost.den > lost.num
    assert not t.references_kept("Sin referencias aquí", "Mana").applicable
    assert t.placeholder_leak("Kay ZXQREF3QXZ qillqa").value == 1.0 and t.placeholder_leak("Kay qillqa").value == 0.0
    assert t.language_ok("Imaynalla kachkanki, wiraqucha, kay wasipi llamk'asqaykimanta").value == 1.0
    assert t.language_ok("Esta es una frase escrita completamente en español").value == 0.0
    assert t.copy_score("la pension de alimentos", "la pension de alimentos").value == 1.0
    assert t.coverage(["abcdefghij"], "").value == 0.0
    assert t.coverage(["abcdefghij"], "abcdefghij").value == pytest.approx(1.0)


def test_glossary_adherence_counts_only_terms_present_in_the_source():
    glossary = [("juez", ["kuskachaq", "kushkachaq"]), ("fiscal", ["huchachaq"])]
    assert t.glossary_adherence("El juez decide", "Kuskachaqmi taqwin", glossary).value == 1.0
    assert t.glossary_adherence("El juez y el fiscal", "Kuskachaqmi rimarin", glossary).value == 0.5
    assert not t.glossary_adherence("Una frase sin términos", "Kay", glossary).applicable
    assert not t.glossary_adherence("El juez", "Kay", []).applicable


def test_round_trip_is_a_cosine_over_injected_embeddings():
    vectors = {"original": [1.0, 0.0], "igual": [1.0, 0.0], "otro": [0.0, 1.0]}
    embed = lambda texts: [vectors[x] for x in texts]  # noqa: E731
    assert t.round_trip("original", "igual", embed).value == pytest.approx(1.0)
    assert t.round_trip("original", "otro", embed).value == pytest.approx(0.0)
    assert not t.round_trip("original", None, embed).applicable and not t.round_trip("original", "igual", None).applicable


def test_the_identity_baseline_is_the_floor_and_is_flagged_as_low_quality(pairs):
    report = evaluate_translation(pairs, identity_outputs(pairs), system="identity")
    assert report["n_scored"] == len(pairs) and report["n_errors"] == 0
    assert report["metrics"]["chrf++"]["macro"]["value"] < 0.2
    assert report["metrics"]["copy_rate"]["macro"]["value"] == pytest.approx(1.0)
    assert report["metrics"]["language_ok"]["macro"]["value"] == 0.0
    assert report["metrics"]["round_trip"]["macro"]["value"] is None
    assert set(report["qe_vs_chrf"]) == {"baja"}
    assert set(report["by_kind"]) == {"sentence", "article", "title", "term"} and set(report["by_variant"]) == {"cusco-collao", "chanka", "sureno-sin-confirmar"}


def test_references_used_as_output_score_perfectly_and_qe_separates_good_from_bad(pairs):
    outputs = {p.id: Output(p.references_qu[0]) for p in pairs}
    report = evaluate_translation(pairs, outputs, system="oracle")
    assert report["metrics"]["chrf++"]["macro"]["value"] == pytest.approx(1.0)
    assert report["metrics"]["ter"]["macro"]["value"] == pytest.approx(0.0)
    assert report["corpus"]["bleu"] == pytest.approx(100.0) and report["corpus"]["chrf++"] == pytest.approx(100.0)
    assert report["metrics"]["placeholder_leak"]["macro"]["value"] == 0.0
    # Los originales largos (artículos) sí permiten confirmar el idioma; las frases de 2-3 palabras quedan en «media».
    articles = evaluate_translation([p for p in pairs if p.kind == "article"], outputs, system="oracle")
    assert articles["qe_vs_chrf"]["alta"]["n"] >= 0.8 * articles["n_scored"]
    short = evaluate_translation([p for p in pairs if p.kind == "term"], outputs, system="oracle")
    assert "alta" not in short["qe_vs_chrf"]


def test_missing_and_failed_outputs_are_errors_not_zeros(pairs):
    subset = pairs[:5]
    outputs = {p.id: Output(p.references_qu[0]) for p in subset[:3]}
    outputs[subset[3].id] = Output("", success=False, error="TimeoutError")
    report = evaluate_translation(subset, outputs)
    assert report["n_scored"] == 3 and report["n_errors"] == 2
    assert {e["error"] for e in report["errors"]} == {"TimeoutError", "sin salida"}
    assert report["metrics"]["chrf++"]["macro"]["value"] == pytest.approx(1.0)


def test_precomputed_round_trip_enters_the_report(pairs):
    pair = pairs[0]
    report = evaluate_translation([pair], {pair.id: Output(pair.references_qu[0], round_trip=0.91)})
    assert report["metrics"]["round_trip"]["macro"]["value"] == pytest.approx(0.91)


def test_language_id_heuristic_is_measured_on_the_gold_itself(pairs):
    check = language_id_check(pairs)
    assert check["references"]["rate"] >= 0.85 and check["sources"]["rate"] >= 0.9
    assert check["references"]["n"] > 100 and check["sources"]["n"] > 100


async def test_translation_suite_writes_offline_baseline_and_replays_a_recorded_cassette(tmp_path, monkeypatch, pairs):
    path, report = await runner.run_translation(source="offline", results_dir=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["meta"]["answer_source"] == "identity_baseline" and saved["meta"]["judge_available"] is False
    assert saved["system"] == "identity" and saved["gold"]["adjudicated"] == 0 and saved["meta"]["gold_hash"]

    async def fake_live(pair):
        return Output(pair.references_qu[0], back_translation=pair.source_es, round_trip=0.9).to_json()

    monkeypatch.setattr(runner, "live_translation", fake_live)
    cassette = tmp_path / "translation.cassette.json"
    _, recorded = await runner.run_translation(source="live", cassette_path=cassette, results_dir=tmp_path)
    assert recorded["system"] == "google_translate" and recorded["metrics"]["chrf++"]["macro"]["value"] == pytest.approx(1.0)

    async def never(pair):
        raise AssertionError("replay no debe llamar al proveedor")

    monkeypatch.setattr(runner, "live_translation", never)
    _, replayed = await runner.run_translation(source="cassette", cassette_path=cassette, results_dir=tmp_path)
    assert replayed["metrics"] == recorded["metrics"] and replayed["metrics"]["round_trip"]["macro"]["value"] == pytest.approx(0.9)
    _, missing = await runner.run_translation(source="cassette", cassette_path=tmp_path / "vacio.json", results_dir=tmp_path)
    assert missing["n_scored"] == 0 and missing["n_errors"] == len(pairs)
    assert translation_eval.HEADLINE == "chrf++"
