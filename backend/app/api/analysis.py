"""Direct image and video analysis for backend integration tests.

These routes are not the product upload flow. The extension and dashboard do
not submit files here.
"""

import sqlite3

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.media import analysis_service
from app.media.analysis_service import AnalysisRejected, analyze_bytes, load_report
from app.models.video_aggregation import POLICY_V1, POLICY_V2

router = APIRouter(tags=["analysis"])


def _detector(request: Request):
    return getattr(request.app.state, "detector", None)


def _read(upload: UploadFile, limit: int) -> bytes:
    return upload.file.read(limit + 1)


def _run(data: bytes, expected: str, request: Request, aggregation_policy: str | None = None) -> dict:
    try:
        report = analyze_bytes(
            data,
            expected=expected,
            detector=_detector(request),
            aggregation_policy=aggregation_policy,
        )
    except AnalysisRejected as rejected:
        if rejected.report is not None and rejected.report["status"] != "completed":
            raise HTTPException(status_code=rejected.status_code, detail=rejected.report) from None
        raise HTTPException(
            status_code=rejected.status_code,
            detail={"code": rejected.code, "message": rejected.message, "status": "failed", "result": None},
        ) from None
    except sqlite3.Error:
        raise HTTPException(status_code=500, detail="The analysis could not be saved.") from None
    if report["status"] != "completed":
        raise HTTPException(status_code=422, detail=report)
    return report


@router.post("/api/analyze/image")
def analyze_image(request: Request, file: UploadFile = File(...)) -> dict:
    return _run(_read(file, analysis_service.IMAGE_MAX_BYTES), "image", request)


@router.post("/api/analyze/video")
def analyze_video(
    request: Request,
    file: UploadFile = File(...),
    aggregation_policy: str = POLICY_V2,
) -> dict:
    if aggregation_policy not in {POLICY_V1, POLICY_V2}:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_aggregation_policy",
                "message": "aggregation_policy must be video_aggregation_v1 or video_aggregation_v2.",
                "status": "failed",
                "result": None,
            },
        )
    return _run(
        _read(file, analysis_service.VIDEO_MAX_BYTES),
        "video",
        request,
        aggregation_policy=aggregation_policy,
    )


@router.get("/api/reports/{report_id}")
def get_analysis_report(report_id: str) -> dict:
    report = load_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} was not found.")
    if report["status"] != "completed":
        raise HTTPException(status_code=409, detail=report)
    return report
