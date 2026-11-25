"""Admin knowledge-graph and SAT-Graph inspection/search endpoints."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from config.settings import settings
from retrieval.sat import SATRetriever, SearchPlan
from retrieval.voyage import VoyageError, VoyageProvider, connect_surreal_voyage
from security import limiter, verify_admin_api_key

router = APIRouter(tags=["sat-admin"])


@router.get("/knowledge-graph")
async def get_knowledge_graph(
    engine: str | None = None, _auth: bool = Depends(verify_admin_api_key)
):
    import main as runtime

    engine = engine or settings.RAG_ENGINE.lower()
    try:
        if engine == "sat":
            graph_data = await asyncio.to_thread(
                lambda: runtime.sat_graph_store().export()
            )
            return {"success": True, "graph": graph_data}
        if engine != "lightrag":
            raise HTTPException(422, "Unknown graph engine")
        if runtime.app.state.rag_engine is None:
            raise HTTPException(409, "LightRAG is disabled in SAT mode")
        graph_data = await runtime.app.state.rag_engine.get_knowledge_graph()
        return {"success": True, "graph": graph_data}
    except HTTPException:
        raise
    except Exception as error:
        runtime._log_failure("knowledge_graph_read_failed", error)
        raise HTTPException(500, "Failed to get knowledge graph")


@router.get("/sat-graph/resolve")
async def resolve_sat_version(
    resource_id: str,
    component: str,
    as_of: str,
    _auth: bool = Depends(verify_admin_api_key),
):
    import main as runtime

    try:
        return await asyncio.to_thread(
            lambda: runtime.sat_graph_store().resolve(resource_id, component, as_of)
        )
    except ValueError:
        raise HTTPException(422, "Invalid SAT query")
    except Exception as error:
        runtime._log_failure("sat_graph_read_failed", error)
        raise HTTPException(500, "Failed to read SAT graph")


@router.get("/sat-graph/structure")
async def sat_candidate_structure(
    evidence_id: str,
    parse_id: str | None = None,
    _auth: bool = Depends(verify_admin_api_key),
):
    import main as runtime

    try:
        return await asyncio.to_thread(
            lambda: runtime.sat_graph_store().structure(evidence_id, parse_id)
        )
    except ValueError:
        raise HTTPException(
            422, "Missing or ambiguous SAT structure; specify a valid parse_id"
        )
    except Exception as error:
        runtime._log_failure("sat_structure_read_failed", error)
        raise HTTPException(500, "Failed to read SAT structure")


@router.post("/sat-graph/search")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def search_sat_graph(
    request: Request,
    plan: SearchPlan,
    use_voyage: bool = False,
    _auth: bool = Depends(verify_admin_api_key),
):
    """Ruta experimental admin. Egreso Voyage solo con opt-in explícito por consulta."""
    import main as runtime

    def retrieve():
        provider = None
        if use_voyage:
            provider = VoyageProvider(
                settings.VOYAGE_API_KEY.get_secret_value(),
                connect=connect_surreal_voyage,
                dimension=settings.VOYAGE_DIMENSION,
                daily_requests=settings.VOYAGE_DAILY_REQUESTS,
                daily_token_reservation=settings.VOYAGE_DAILY_TOKEN_RESERVATION,
                requests_per_minute=settings.VOYAGE_REQUESTS_PER_MINUTE,
                token_bound_per_minute=settings.VOYAGE_TOKEN_BOUND_PER_MINUTE,
            )
        graph = runtime.sat_graph_store().export()
        return SATRetriever(graph).search(plan, provider=provider)

    try:
        return await asyncio.to_thread(retrieve)
    except VoyageError:
        raise HTTPException(503, "Voyage unavailable or local budget exhausted")
    except ValueError:
        raise HTTPException(422, "Invalid SAT retrieval parameters")
    except Exception as error:
        runtime._log_failure("sat_graph_search_failed", error, request)
        raise HTTPException(500, "Failed to search SAT graph")


@router.get("/sat-graph/history")
async def sat_graph_history(
    resource_id: str,
    component: str,
    _auth: bool = Depends(verify_admin_api_key),
):
    import main as runtime

    try:
        return await asyncio.to_thread(
            lambda: SATRetriever(runtime.sat_graph_store().export()).history(
                resource_id, component
            )
        )
    except Exception as error:
        runtime._log_failure("sat_graph_history_failed", error)
        raise HTTPException(500, "Failed to read SAT history")
