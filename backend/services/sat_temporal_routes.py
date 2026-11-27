"""Authenticated FastAPI routes for the SAT-Graph Viewer temporal projection."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from services.quality_access import require_quality_admin
from services.sat_corpus_routes import call, editor
from services.sat_temporal_projection import (
    UnknownResourceError,
    ViewerDataset,
    bundled_viewer_samples,
    project_sat_graph_to_viewer_dataset,
)

router = APIRouter(
    prefix="/sat-graph/review/temporal",
    tags=["SAT temporal viewer"],
    dependencies=[Depends(require_quality_admin)],
)


@router.get("/dataset/{resource_id}", response_model=ViewerDataset)
async def get_resource_temporal_dataset(
    resource_id: str,
    include_editorial_history: bool = True,
) -> ViewerDataset:
    def build() -> ViewerDataset:
        graph = editor().store.export()
        try:
            return project_sat_graph_to_viewer_dataset(
                graph,
                resource_id=resource_id,
                include_editorial_history=include_editorial_history,
            )
        except UnknownResourceError as exc:
            raise HTTPException(404, str(exc)) from exc

    return await call(build)


@router.get("/dataset", response_model=ViewerDataset)
async def get_corpus_temporal_dataset(
    include_editorial_history: bool = True,
) -> ViewerDataset:
    def build() -> ViewerDataset:
        graph = editor().store.export()
        return project_sat_graph_to_viewer_dataset(
            graph,
            resource_id=None,
            include_editorial_history=include_editorial_history,
        )

    return await call(build)


@router.get("/samples")
async def get_temporal_samples() -> dict[str, list[dict]]:
    return {"samples": bundled_viewer_samples()}
