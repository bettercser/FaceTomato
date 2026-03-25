"""Interview review APIs."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Body, Depends, HTTPException

from app.schemas.interview_review import (
    ReviewExportReportResponse,
    ReviewGenerateReportResponse,
    ReviewOptimizationRequest,
    ReviewOptimizationResponse,
    ReviewSessionDetail,
    ReviewSessionListResponse,
    ReviewUploadSessionResponse,
)
from app.schemas.mock_interview import MockInterviewSessionSnapshot
from app.services.interview_review_service import (
    InterviewReviewNotEligibleError,
    InterviewReviewService,
    get_interview_review_service,
)

router = APIRouter(prefix="/interview-reviews", tags=["interview-reviews"])
logger = logging.getLogger(__name__)


def _snapshot_log_fields(snapshot: MockInterviewSessionSnapshot | None) -> dict[str, object]:
    if snapshot is None:
        return {
            "has_snapshot": False,
            "status": None,
            "interview_closed": None,
            "current_round": None,
            "total_rounds": None,
            "message_count": None,
            "conversation_length": None,
            "has_runtime_override": False,
        }
    return {
        "has_snapshot": True,
        "status": snapshot.status,
        "interview_closed": snapshot.interviewState.closed,
        "current_round": snapshot.interviewState.currentRound,
        "total_rounds": snapshot.interviewPlan.total_rounds,
        "message_count": len(snapshot.messages),
        "conversation_length": len(snapshot.messages),
        "has_runtime_override": snapshot.runtimeConfig is not None,
    }


def _route_log_fields(
    session_id: str,
    *,
    topic_id: str | None = None,
    snapshot: MockInterviewSessionSnapshot | None = None,
    conversation_length: int | None = None,
    has_runtime_override: bool | None = None,
) -> dict[str, object]:
    fields = {
        "session_id": session_id,
        "topic_id": topic_id,
        **_snapshot_log_fields(snapshot),
    }
    if conversation_length is not None:
        fields["conversation_length"] = conversation_length
    if has_runtime_override is not None:
        fields["has_runtime_override"] = has_runtime_override
    return fields


@router.get("", response_model=ReviewSessionListResponse)
async def list_interview_reviews(
    service: InterviewReviewService = Depends(get_interview_review_service),
) -> ReviewSessionListResponse:
    return ReviewSessionListResponse(items=service.list_reviews())


@router.post("/upload", response_model=ReviewUploadSessionResponse)
async def upload_interview_review_snapshot(
    snapshot: MockInterviewSessionSnapshot,
    service: InterviewReviewService = Depends(get_interview_review_service),
) -> ReviewUploadSessionResponse:
    start = time.perf_counter()
    logger.info(
        "interview review upload request",
        extra=_route_log_fields(snapshot.sessionId, snapshot=snapshot),
    )
    try:
        result = service.upload_snapshot(snapshot)
    except InterviewReviewNotEligibleError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.warning(
            "interview review upload rejected",
            extra={
                **_route_log_fields(snapshot.sessionId, snapshot=snapshot),
                "report_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    logger.info(
        "interview review upload completed",
        extra={
            **_route_log_fields(snapshot.sessionId, snapshot=snapshot),
            "report_status": result.reportStatus,
            "elapsed_ms": elapsed_ms,
        },
    )
    return result


@router.get("/{session_id}", response_model=ReviewSessionDetail)
async def get_interview_review_detail(
    session_id: str,
    service: InterviewReviewService = Depends(get_interview_review_service),
) -> ReviewSessionDetail:
    detail = service.get_review(session_id)
    if detail is None:
        raise HTTPException(status_code=409, detail="Interview review report is not ready")
    return detail


@router.post("/{session_id}/generate", response_model=ReviewGenerateReportResponse)
async def generate_interview_review(
    session_id: str,
    snapshot: MockInterviewSessionSnapshot | None = Body(default=None),
    service: InterviewReviewService = Depends(get_interview_review_service),
) -> ReviewGenerateReportResponse:
    start = time.perf_counter()
    logger.info(
        "interview review generate request",
        extra=_route_log_fields(session_id, snapshot=snapshot),
    )
    if snapshot is not None and snapshot.sessionId != session_id:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.warning(
            "interview review generate rejected",
            extra={
                **_route_log_fields(session_id, snapshot=snapshot),
                "report_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=400, detail="Session id mismatch")
    try:
        result = service.generate_review(session_id, snapshot=snapshot)
    except InterviewReviewNotEligibleError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.warning(
            "interview review generate rejected",
            extra={
                **_route_log_fields(session_id, snapshot=snapshot),
                "report_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.info(
            "interview review generate not found",
            extra={
                **_route_log_fields(session_id, snapshot=snapshot),
                "report_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=404, detail="Mock interview session not found")
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    logger.info(
        "interview review generate completed",
        extra={
            **_route_log_fields(session_id, snapshot=snapshot),
            "report_status": result.reportStatus,
            "elapsed_ms": elapsed_ms,
        },
    )
    return result


@router.post("/{session_id}/export", response_model=ReviewExportReportResponse)
async def export_interview_review(
    session_id: str,
    service: InterviewReviewService = Depends(get_interview_review_service),
) -> ReviewExportReportResponse:
    start = time.perf_counter()
    logger.info(
        "interview review export request",
        extra=_route_log_fields(session_id),
    )
    try:
        result = service.export_review(session_id)
    except InterviewReviewNotEligibleError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.warning(
            "interview review export rejected",
            extra={
                **_route_log_fields(session_id),
                "export_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.info(
            "interview review export not found",
            extra={
                **_route_log_fields(session_id),
                "export_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=404, detail="Mock interview session not found")
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    logger.info(
        "interview review export completed",
        extra={
            **_route_log_fields(session_id),
            "export_status": result.exportStatus,
            "elapsed_ms": elapsed_ms,
        },
    )
    return result


@router.post("/{session_id}/topics/{topic_id}/optimize", response_model=ReviewOptimizationResponse)
async def optimize_interview_review_topic(
    session_id: str,
    topic_id: str,
    request: ReviewOptimizationRequest,
    service: InterviewReviewService = Depends(get_interview_review_service),
) -> ReviewOptimizationResponse:
    start = time.perf_counter()
    logger.info(
        "interview review optimize request",
        extra=_route_log_fields(
            session_id,
            topic_id=topic_id,
            conversation_length=len(request.conversation),
            has_runtime_override=request.runtimeConfig is not None,
        ),
    )
    if request.sessionId != session_id or request.topicId != topic_id:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.warning(
            "interview review optimize rejected",
            extra={
                **_route_log_fields(
                    session_id,
                    topic_id=topic_id,
                    conversation_length=len(request.conversation),
                    has_runtime_override=request.runtimeConfig is not None,
                ),
                "report_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=400, detail="Session or topic id mismatch")
    try:
        result = service.optimize_topic(request)
    except InterviewReviewNotEligibleError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.warning(
            "interview review optimize rejected",
            extra={
                **_route_log_fields(
                    session_id,
                    topic_id=topic_id,
                    conversation_length=len(request.conversation),
                    has_runtime_override=request.runtimeConfig is not None,
                ),
                "report_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        logger.info(
            "interview review optimize not found",
            extra={
                **_route_log_fields(
                    session_id,
                    topic_id=topic_id,
                    conversation_length=len(request.conversation),
                    has_runtime_override=request.runtimeConfig is not None,
                ),
                "report_status": None,
                "elapsed_ms": elapsed_ms,
            },
        )
        raise HTTPException(status_code=404, detail="Interview review session or topic not found")
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    logger.info(
        "interview review optimize completed",
        extra={
            **_route_log_fields(
                session_id,
                topic_id=topic_id,
                conversation_length=len(result.conversation),
                has_runtime_override=request.runtimeConfig is not None,
            ),
            "report_status": "ready",
            "elapsed_ms": elapsed_ms,
        },
    )
    return result
