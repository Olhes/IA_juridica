import json

import pytest
from pydantic import ValidationError

from main import LegalQueryRequest, _ndjson_event


def test_query_request_forbids_unknown_fields_and_empty_query():
    assert LegalQueryRequest(query="licencia").language == "spanish"
    for data in ({"query": ""}, {"query": "licencia", "effective_date": "2024-01-01"}):
        with pytest.raises(ValidationError):
            LegalQueryRequest.model_validate(data)


def test_query_length_bounds_and_language_is_supported():
    assert len(LegalQueryRequest(query="x" * 8000).query) == 8000
    assert LegalQueryRequest(query=" x ", language="quechua").query == "x"
    with pytest.raises(ValidationError):
        LegalQueryRequest(query="x", language="custom")
    for query in ("", "  ", "x" * 8001):
        with pytest.raises(ValidationError):
            LegalQueryRequest(query=query)


def test_ndjson_event_has_single_line_and_unicode():
    encoded = _ndjson_event({"type": "chunk", "delta": "Artículo único"})
    assert encoded.endswith("\n") and encoded.count("\n") == 1
    assert json.loads(encoded) == {"type": "chunk", "delta": "Artículo único"}


@pytest.mark.asyncio
async def test_rag_result_contract_is_local_not_temporal(rag):
    result = await rag.query_with_rerank("licencia", top_k=2)
    assert set(result) == {
        "answer",
        "documents",
        "rerank_scores",
        "sources",
        "method",
        "total_candidates",
    }
    assert all(
        {"id", "document_id", "content", "metadata", "relevance_score"} <= doc.keys()
        for doc in result["documents"]
    )
    assert all(0 <= score <= 1 for score in result["rerank_scores"])


@pytest.mark.parametrize(
    "status_code, description",
    [
        ("500", "PDF generation failed"),
        ("503", "PDF generation unavailable"),
    ],
)
def test_pdf_report_errors_are_documented_in_openapi(api, status_code, description):
    client, _, _ = api
    responses = client.get("/openapi.json").json()["paths"]["/generate-pdf-report"][
        "post"
    ]["responses"]
    assert responses[status_code]["description"] == description
    assert "200" in responses
    assert "422" in responses
