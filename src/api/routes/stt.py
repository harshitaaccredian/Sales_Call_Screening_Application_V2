"""
STT routes — /api/stt/*

POST /api/stt/submit
    Submit an audio file for async Google Cloud transcription.
    Accepts either a multipart file upload or a JSON body with audio_path.
    Returns a job_id for polling.

GET /api/stt/status/{job_id}
    Poll the current status of an STT job.
    Calls Google's operations API to get live progress and updates the DB.

GET /api/stt/result/{job_id}
    Fetch the final transcript once status == DONE.
    Returns 409 if the job is not yet complete.
"""

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.api.db import get_db, new_session
from src.api.models.jobs import SttJob
from src.api.models.schemas import (
    SttJobStatus,
    SttResultResponse,
    SttSubmitResponse,
)
from src.api.services import stt_service

router = APIRouter(prefix="/api/stt", tags=["STT"])

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_UPLOAD_DIR = _PROJECT_ROOT / "output" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_job_or_404(job_id: str, db: Session) -> SttJob:
    job = db.get(SttJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"STT job '{job_id}' not found.")
    return job


def _sync_poll_and_update(job_id: str) -> None:
    """
    Poll Google for the latest operation status and update the DB.
    Runs synchronously — call from a BackgroundTask or directly.
    """
    db = new_session()
    try:
        job = db.get(SttJob, job_id)
        if not job or job.status in ("DONE", "FAILED", "EXPIRED"):
            return

        try:
            done, utterances = stt_service.poll_stt(job.operation_name, job.gcs_uri)
        except RuntimeError as exc:
            err = str(exc)
            job.status = "EXPIRED" if "no longer exists" in err else "FAILED"
            job.error = err
            db.commit()
            return

        if done:
            transcript_path, _ = stt_service.save_transcript(job.id, job.audio_path, utterances)
            job.status = "DONE"
            job.transcript_path = transcript_path
        else:
            job.status = "PROCESSING"

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/stt/submit  (Form field — server-local file path)
# ---------------------------------------------------------------------------

@router.post("/submit", response_model=SttSubmitResponse, status_code=202)
def submit_stt_path(
    background_tasks: BackgroundTasks,
    audio_path: str = Form(..., description="Server-local path to the audio file. Forward or back slashes both accepted."),
    db: Session = Depends(get_db),
) -> SttSubmitResponse:
    """
    Submit an audio file (by server-local path) for async STT.

    Send as **form data** (`Content-Type: application/x-www-form-urlencoded`).
    Using form data avoids JSON backslash-escaping issues on Windows paths.

    The file must already exist on the server. Use POST /api/stt/submit/upload
    to upload a file from your client instead.
    """
    from src.api.services.stt_service import GCS_HTTPS_PREFIX

    audio_path = audio_path.strip()
    is_gcs_url = audio_path.startswith(GCS_HTTPS_PREFIX)

    if is_gcs_url:
        # GCS HTTPS URL — no local existence check needed.
        resolved_path = audio_path
    else:
        resolved = Path(audio_path.replace("\\", "/"))
        if not resolved.exists():
            raise HTTPException(
                status_code=422,
                detail=f"Audio file not found: {audio_path}",
            )
        resolved_path = str(resolved)

    # Create the DB record first so we have an ID to return.
    job = SttJob(audio_path=resolved_path, status="PENDING")
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        operation_name, gcs_uri = stt_service.submit_stt(resolved_path)
    except (ValueError, RuntimeError) as exc:
        job.status = "FAILED"
        job.error = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job.operation_name = operation_name
    job.gcs_uri = gcs_uri
    job.status = "SUBMITTED"
    db.commit()

    # Trigger background processing immediately
    background_tasks.add_task(_sync_poll_and_update, job.id)

    return SttSubmitResponse(
        job_id=job.id,
        status="SUBMITTED",
        operation_name=operation_name,
        message="STT job submitted. Processing started in background.",
    )


# ---------------------------------------------------------------------------
# POST /api/stt/submit/upload  (multipart file upload)
# ---------------------------------------------------------------------------

@router.post("/submit/upload", response_model=SttSubmitResponse, status_code=202)
def submit_stt_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SttSubmitResponse:
    """
    Upload an audio file and submit it for async STT.

    The file is saved to output/uploads/<filename> before submission.
    """
    dest = _UPLOAD_DIR / (file.filename or "audio_upload")
    # Avoid collisions by appending job ID later — use a temp name first.
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    job = SttJob(audio_path=str(dest), status="PENDING")
    db.add(job)
    db.commit()
    db.refresh(job)

    # Rename to include the job ID so uploads are uniquely identified.
    final_dest = _UPLOAD_DIR / f"{job.id}_{dest.name}"
    dest.rename(final_dest)
    job.audio_path = str(final_dest)

    try:
        operation_name, gcs_uri = stt_service.submit_stt(str(final_dest))
    except (ValueError, RuntimeError) as exc:
        job.status = "FAILED"
        job.error = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job.operation_name = operation_name
    job.gcs_uri = gcs_uri
    job.status = "SUBMITTED"
    db.commit()

    # Trigger background processing immediately
    background_tasks.add_task(_sync_poll_and_update, job.id)

    return SttSubmitResponse(
        job_id=job.id,
        status="SUBMITTED",
        operation_name=operation_name,
        message="STT job submitted. Processing started in background.",
    )


# ---------------------------------------------------------------------------
# GET /api/stt/status/{job_id}
# ---------------------------------------------------------------------------

@router.get("/status/{job_id}", response_model=SttJobStatus)
def get_stt_status(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> SttJobStatus:
    """
    Return the current status of an STT job.

    For jobs in SUBMITTED or PROCESSING state this endpoint triggers a
    background poll of Google's operations API so the DB stays current.
    The response reflects the status *before* that background update — the
    client should poll again shortly to see the updated status.
    """
    job = _get_job_or_404(job_id, db)

    # Kick off a background poll for in-progress jobs.
    if job.status in ("SUBMITTED", "PROCESSING"):
        background_tasks.add_task(_sync_poll_and_update, job_id)

    return SttJobStatus(
        job_id=job.id,
        status=job.status,
        operation_name=job.operation_name,
        audio_path=job.audio_path,
        transcript_path=job.transcript_path,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/stt/result/{job_id}
# ---------------------------------------------------------------------------

@router.get("/result/{job_id}", response_model=SttResultResponse)
def get_stt_result(
    job_id: str,
    db: Session = Depends(get_db),
) -> SttResultResponse:
    """
    Fetch the completed transcript for a finished STT job.

    Returns 409 Conflict if the job has not yet reached DONE status.
    """
    job = _get_job_or_404(job_id, db)

    if job.status != "DONE":
        raise HTTPException(
            status_code=409,
            detail=f"STT job is not complete yet. Current status: {job.status}",
        )

    utterances = None
    if job.transcript_path:
        # save_transcript returns the VTT path, but also saves a JSON version
        # with the same base name for API consumption.
        transcript_file = Path(job.transcript_path)
        json_file = transcript_file.with_suffix(".json")
        
        if json_file.exists():
            data = json.loads(json_file.read_text(encoding="utf-8"))
            utterances = data.get("utterances", [])
        elif transcript_file.exists() and transcript_file.suffix == ".json":
            # Fallback if transcript_path itself is already JSON
            data = json.loads(transcript_file.read_text(encoding="utf-8"))
            utterances = data.get("utterances", [])

    return SttResultResponse(
        job_id=job.id,
        status=job.status,
        transcript_path=job.transcript_path,
        utterances=utterances,
    )
