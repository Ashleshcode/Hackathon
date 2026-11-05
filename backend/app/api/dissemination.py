"""Read imported Twitter15 and Twitter16 propagation cases."""

from fastapi import APIRouter, HTTPException

from app.dissemination.repository import get_case, get_graph, list_cases

router = APIRouter(prefix="/api/dissemination", tags=["dissemination"])


@router.get("/cases")
def dissemination_cases() -> list[dict]:
    return list_cases()


@router.get("/cases/{case_id}")
def dissemination_case(case_id: str) -> dict:
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Dissemination case {case_id} was not found.")
    return case


@router.get("/cases/{case_id}/graph")
def dissemination_graph(case_id: str) -> dict:
    graph = get_graph(case_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Dissemination case {case_id} was not found.")
    return graph
