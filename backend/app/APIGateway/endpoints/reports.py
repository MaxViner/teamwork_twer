"""Экспорт транскрипта, поиска, отчёта и evidence JSON."""


import json

from fastapi import (
    APIRouter,
    HTTPException,
)
from fastapi.responses import (
    FileResponse,
    Response,
)

from app.APIGateway.jobs import (
    LOCK,
    load_job,
)
from app.search import search_job
from app.services.audioService.transcript import (
    to_srt,
    to_vtt,
    transcript_payload,
)
from app.services.reportingService.reporting import (
    render_evidence_json,
    render_report,
)
from app.storage import StorageService


router = APIRouter(prefix="/api/jobs")



@router.get("/{job_id}/transcript.json")
def export_transcript_json(job_id: str):
    return transcript_payload(
        load_job(job_id),
    )



@router.get("/{job_id}/transcript.vtt")
def export_transcript_vtt(job_id: str):
    job = load_job(job_id)
    payload = transcript_payload(job)


    return Response(
        content=to_vtt(
            payload,
            job.get("name") or "Расшифровка",
        ),
        media_type="text/vtt",
        headers={
            "Content-Disposition": (
                'attachment; filename="transcript.vtt"'
            ),
        },
    )



@router.get("/{job_id}/transcript.srt")
def export_transcript_srt(job_id: str):
    payload = transcript_payload(
        load_job(job_id),
    )


    return Response(
        content=to_srt(payload),
        media_type="application/x-subrip",
        headers={
            "Content-Disposition": (
                'attachment; filename="transcript.srt"'
            ),
        },
    )



@router.get("/{job_id}/search")
def search_inside_job(
    job_id: str,
    q: str = "",
    limit: int = 60,
):
    job = load_job(job_id)


    return {
        "query": q,
        "results": search_job(
            job,
            q,
            limit=max(
                1,
                min(200, limit),
            ),
        ),
    }



@router.get("/{job_id}/export")
def export_job(job_id: str):
    load_job(job_id)
    storage = StorageService.for_job(job_id)


    return FileResponse(
        storage.job_json,
        media_type="application/json",
        filename=f"{job_id}.json",
    )



@router.delete("/{job_id}")
def delete_job(job_id: str):
    with LOCK:
        job = load_job(job_id)


        if job.get("status") in (
            "queued",
            "running",
        ):
            raise HTTPException(
                409,
                "Нельзя удалить выполняющееся задание.",
            )


        StorageService.for_job(
            job_id,
        ).delete_job()


    return {"status": "deleted"}



@router.get("/{job_id}/evidence")
def export_evidence(job_id: str):
    job = load_job(job_id)
    payload = render_evidence_json(job)


    return Response(
        content=json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="evidence.json"'
            ),
        },
    )



@router.get("/{job_id}/report")
def export_markdown_report(job_id: str):
    with LOCK:
        job = load_job(job_id)


        if job.get("status") in (
            "queued",
            "running",
        ):
            raise HTTPException(
                409,
                "Дождитесь завершения обработки "
                "перед формированием отчёта.",
            )


        report = render_report(job)


        StorageService.for_job(
            job_id,
        ).save_report(report)


    return Response(
        content=report.encode("utf-8"),
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                'attachment; filename="report.md"'
            ),
        },
    )