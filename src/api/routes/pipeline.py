"""
Pipeline routes — /api/pipeline/*

POST /api/pipeline/submit
    Submit a full call-quality pipeline run. Accepts an audio file OR a
    pre-existing transcript (SRT/VTT/JSON/TXT) plus the course CSV.
    Returns a pipeline_id for polling.

GET /api/pipeline/status/{pipeline_id}
    Poll the current step and status of a pipeline run.

GET /api/pipeline/result/{pipeline_id}
    Fetch the output file paths once status == DONE.

--- Background task lifecycle ---

When input is audio:
  1. submit_stt() → SttJob created, STT submitted to the configured provider.
  2. Background task processes STT.
  3. Once STT is DONE, pipeline proceeds: clean → analyze → report.

When input is SRT/VTT/JSON/TXT:
  1. No STT step.
  2. Background task runs: clean → analyze → report immediately.

Each step updates PipelineJob.current_step and .status in the DB so the
status endpoint always reflects the live position in the pipeline.

--- Server restart resilience ---

The app startup handler (in main.py) calls resume_stuck_pipelines() to
restart background tasks for any jobs stuck in a non-terminal state. This
handles the case where the server restarted mid-pipeline.
"""

import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from src.api.db import get_db, new_session
from src.api.models.jobs import PipelineJob, SttJob
from src.api.models.schemas import (
    PipelineJobStatus,
    PipelineResultResponse,
    PipelineSubmitResponse,
)
from src.api.services import analysis_service, clean_service, report_service, stt_service
from src.api.services.assessment_service import run_assessment


router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])

# How long to wait between STT polls inside the background task.
STT_POLL_INTERVAL_SEC = 15

# Maximum time to wait for STT before marking the pipeline FAILED.
STT_MAX_WAIT_SEC = 60 * 60  # 1 hour

_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".webm"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_pipeline_or_404(pipeline_id: str, db: Session) -> PipelineJob:
    job = db.get(PipelineJob, pipeline_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline job '{pipeline_id}' not found.",
        )
    return job


def _update_pipeline(pipeline_id: str, **kwargs) -> None:
    """Update pipeline job fields in a new DB session. Safe for background tasks."""
    db = new_session()
    try:
        job = db.get(PipelineJob, pipeline_id)
        if not job:
            return
        for key, value in kwargs.items():
            setattr(job, key, value)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _fail_pipeline(pipeline_id: str, error: str) -> None:
    _update_pipeline(pipeline_id, status="FAILED", current_step="FAILED", error=error)


def cleanup_empty_job_folders() -> None:
    """Scan data/output for job folders that contain no files and delete them."""
    out_dir = Path(__file__).resolve().parents[3] / "data" / "output"
    if not out_dir.exists():
        return
    for job_dir in out_dir.iterdir():
        if job_dir.is_dir():
            has_files = False
            for root, dirs, files in os.walk(job_dir):
                if files:
                    has_files = True
                    break
            if not has_files:
                try:
                    shutil.rmtree(job_dir)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Core background task
# ---------------------------------------------------------------------------

def _run_pipeline(pipeline_id: str) -> None:
    """
    Full pipeline execution — runs entirely in a background thread.

    Steps:
      1. If audio input: poll STT until DONE (or timeout/error).
      2. Determine the transcript path for cleaning.
      3. Run clean_service.
      4. Run analysis_service.
      5. Run report_service.
    """
    db = new_session()
    try:
        job = db.get(PipelineJob, pipeline_id)
        if not job:
            return
        stt_job_id = job.stt_job_id
        input_path = job.input_path
        course_path = job.course_path
        sales_pitch_path = job.sales_pitch_path
        model = job.model
        rep_id = job.rep_id
        call_id = job.call_id
        sales_rep_name = job.sales_rep_name
        customer_name = job.customer_name
    finally:
        db.close()

    transcript_path: str | None = None
    # Bound on only two of the three paths below — initialise so the
    # already-DONE resume path cannot raise NameError at the clean step.
    rep_speaker_name: str | int | None = None

    # ------------------------------------------------------------------
    # Step 1: STT polling (audio input only)
    # ------------------------------------------------------------------
    if stt_job_id:
        _update_pipeline(pipeline_id, current_step="STT_POLLING", status="STT_POLLING")
        elapsed = 0
        while elapsed < STT_MAX_WAIT_SEC:
            time.sleep(STT_POLL_INTERVAL_SEC)
            elapsed += STT_POLL_INTERVAL_SEC

            db = new_session()
            try:
                stt_job = db.get(SttJob, stt_job_id)
                if not stt_job:
                    _fail_pipeline(pipeline_id, "STT job record disappeared from DB.")
                    return
                op_name = stt_job.operation_name
                gcs_uri = stt_job.gcs_uri
                current_stt_status = stt_job.status
            finally:
                db.close()

            # Already done from a previous poll (e.g. status endpoint ran first).
            if current_stt_status == "DONE":
                db = new_session()
                try:
                    stt_job = db.get(SttJob, stt_job_id)
                    transcript_path = stt_job.transcript_path if stt_job else None
                finally:
                    db.close()
                # Resumed after the transcript was already saved, so
                # save_transcript() never ran in this process. Fall back to
                # rep_id so clean_service can still pick a speaker.
                rep_speaker_name = rep_speaker_name or rep_id
                break

            if current_stt_status in ("FAILED", "EXPIRED"):
                db = new_session()
                try:
                    stt_job = db.get(SttJob, stt_job_id)
                    err = stt_job.error if stt_job else "STT failed"
                finally:
                    db.close()
                _fail_pipeline(pipeline_id, f"STT failed: {err}")
                return

            # Poll STT provider — passes context path so it can find the audio if needed.
            try:
                done, utterances = stt_service.poll_stt(op_name, gcs_uri)
            except RuntimeError as exc:
                err = str(exc)
                status = "EXPIRED" if "no longer exists" in err else "FAILED"
                db = new_session()
                try:
                    stt_job = db.get(SttJob, stt_job_id)
                    if stt_job:
                        stt_job.status = status
                        stt_job.error = err
                        db.commit()
                finally:
                    db.close()
                _fail_pipeline(pipeline_id, f"STT error: {err}")
                return

            if done:
                saved_path, rep_speaker_name = stt_service.save_transcript(pipeline_id, input_path, utterances)
                db = new_session()
                try:
                    stt_job = db.get(SttJob, stt_job_id)
                    if stt_job:
                        stt_job.status = "DONE"
                        stt_job.transcript_path = saved_path
                        db.commit()
                finally:
                    db.close()
                transcript_path = saved_path
                break
            else:
                db = new_session()
                try:
                    stt_job = db.get(SttJob, stt_job_id)
                    if stt_job and stt_job.status != "PROCESSING":
                        stt_job.status = "PROCESSING"
                        db.commit()
                finally:
                    db.close()
        else:
            _fail_pipeline(
                pipeline_id,
                f"STT timed out after {STT_MAX_WAIT_SEC // 60} minutes.",
            )
            return

        if not transcript_path:
            _fail_pipeline(pipeline_id, "STT completed but transcript path is missing.")
            return
    else:
        # Direct transcript input — use the original input path.
        transcript_path = input_path
        rep_speaker_name = rep_id  # local; `job` is detached after db.close()

    # ------------------------------------------------------------------
    # Step 2: Clean
    # ------------------------------------------------------------------
    _update_pipeline(pipeline_id, current_step="CLEANING", status="CLEANING")
    try:
        clean_result = clean_service.run_clean(
            pipeline_id=pipeline_id,
            transcript_path=transcript_path,
            rep_speaker=rep_speaker_name,
            customer_name=customer_name,
            sales_rep_name=sales_rep_name,
        )
    except Exception as exc:
        _fail_pipeline(pipeline_id, f"Cleaning failed: {exc}")
        return

    cleaned_vtt_path = clean_result["cleaned_vtt_path"]
    stats = clean_result["stats"]
    metrics = clean_result["metrics"] 
    _update_pipeline(pipeline_id, cleaned_vtt_path=cleaned_vtt_path)

    # ------------------------------------------------------------------
    # Step 3: Analyze (OpenRouter LLM)
    # ------------------------------------------------------------------
    # _update_pipeline(pipeline_id, current_step="ANALYZING", status="ANALYZING")
    # try:
    #     analysis_result = analysis_service.run_analysis(
    #         pipeline_id=pipeline_id,
    #         cleaned_vtt_path=cleaned_vtt_path,
    #         course_path=course_path,
    #         sales_pitch_path=sales_pitch_path,
    #         model=model,
    #         call_id=call_id,
    #         call_recording_file=input_path if stt_job_id else None,
    #         call_stt_file=transcript_path,
    #         sales_rep_name=stats.get("sales_rep_name"),
    #         sales_rep_id=rep_id,
    #         customer_name=stats.get("customer_name"),
    #         call_duration=stats.get("duration_str"),
    #         no_of_words=stats.get("total_words"),
    #         stats=stats,
    #     )
    # except Exception as exc:
    #     _fail_pipeline(pipeline_id, f"Analysis failed: {exc}")
    #     return

    # report_json_path = analysis_result["report_json_path"]
    # _update_pipeline(pipeline_id, report_json_path=report_json_path)
    # ------------------------------------------------------------------
    # Step 3: Analyze — compliance + methodology in parallel, then score
    # ------------------------------------------------------------------
    _update_pipeline(pipeline_id, current_step="ANALYZING", status="ANALYZING")
    try:
        analysis_result = run_assessment(
            pipeline_id=pipeline_id,
            cleaned_vtt_path=cleaned_vtt_path,
            course_path=course_path,
            sales_pitch_path=sales_pitch_path,
            model=model,
            metrics=metrics,                          # NEW
            call_id=call_id,
            call_recording_file=input_path if stt_job_id else None,
            call_stt_file=transcript_path,
            sales_rep_name=stats.get("sales_rep_name"),
            sales_rep_id=rep_id,
            customer_name=stats.get("customer_name"),
            call_duration=stats.get("duration_str"),
            no_of_words=stats.get("total_words"),
            stats=stats,
        )
    except Exception as exc:
        _fail_pipeline(pipeline_id, f"Analysis failed: {exc}")
        return

    report_json_path = analysis_result["report_json_path"]
    _update_pipeline(
        pipeline_id,
        report_json_path=report_json_path,
        total_score=analysis_result.get("total_score"),
        call_type=analysis_result.get("call_type"),
        trust_stage=analysis_result.get("trust_stage"),
        low_confidence=analysis_result.get("low_confidence"),
        methodology_status=analysis_result.get("methodology_status"),
        rubric_version=analysis_result.get("rubric_version"),
        scoring_version=analysis_result.get("scoring_version"),
    )

    # ------------------------------------------------------------------
    # Step 4: Generate HTML report
    # ------------------------------------------------------------------
    _update_pipeline(pipeline_id, current_step="REPORT_GEN", status="REPORT_GEN")
    try:
        html_path = report_service.run_report_html(pipeline_id, report_json_path)
    except Exception as exc:
        _fail_pipeline(pipeline_id, f"HTML report generation failed: {exc}")
        return

    _update_pipeline(
        pipeline_id,
        current_step="DONE",
        status="DONE",
        report_html_path=html_path,
    )


# ---------------------------------------------------------------------------
# POST /api/pipeline/submit
# ---------------------------------------------------------------------------

@router.post("/submit", response_model=PipelineSubmitResponse, status_code=202)
def submit_pipeline(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    audio_path: str | None = Form(
        None,
        description="Server-local path to audio file. Triggers STT → clean → analyze → report.",
    ),
    transcript_path: str | None = Form(
        None,
        description="Server-local path to transcript (.srt/.vtt/.json/.txt). Skips STT.",
    ),
    course_path: str = Form(..., description="Server-local path to the course-offering CSV."),
    sales_pitch_path: str | None = Form(
        None,
        description="Server-local path to the sales pitch .md file.",
    ),
    model: str | None = Form(
        None,
        description="OpenRouter model identifier. Defaults to OPENROUTER_DEFAULT_MODEL env var.",
    ),
    rep_id: str | None = Form(None, description="Sales rep email or employee ID."),
    call_id: str | None = Form(None, description="CRM call ID."),
    sales_rep_name: str | None = Form(None, description="Expected sales rep name."),
    customer_name: str | None = Form(None, description="Expected customer name."),
) -> PipelineSubmitResponse:
    """
    Submit a full call-quality pipeline run.

    Send as **form data** (`Content-Type: application/x-www-form-urlencoded`).
    This avoids JSON backslash-escaping issues with Windows paths.

    Provide exactly one of:
    - `audio_path`      → STT + clean + analyze + report
    - `transcript_path` → clean + analyze + report (STT skipped)

    `course_path` is required in both modes.
    """
    from src.api.services.stt_service import GCS_HTTPS_PREFIX

    # Strip whitespace that form clients may append, then normalise separators.
    if audio_path:
        audio_path = audio_path.strip()
    if transcript_path:
        transcript_path = transcript_path.strip()
    course_path = course_path.strip()
    if sales_pitch_path:
        sales_pitch_path = sales_pitch_path.strip()

    # Normalise path separators so Windows backslashes work for local paths.
    if audio_path and not audio_path.startswith(GCS_HTTPS_PREFIX):
        audio_path = audio_path.replace("\\", "/")
    if transcript_path:
        transcript_path = transcript_path.replace("\\", "/")
    course_path = course_path.replace("\\", "/")
    if sales_pitch_path:
        sales_pitch_path = sales_pitch_path.replace("\\", "/")

    # --- Validate inputs ---
    if not audio_path and not transcript_path:
        raise HTTPException(
            status_code=422,
            detail="Provide either audio_path or transcript_path.",
        )
    if audio_path and transcript_path:
        raise HTTPException(
            status_code=422,
            detail="Provide either audio_path or transcript_path, not both.",
        )

    input_path = audio_path or transcript_path

    # GCS HTTPS URLs don't need a local existence check.
    is_gcs_url = audio_path and audio_path.startswith(GCS_HTTPS_PREFIX)

    if not is_gcs_url and not Path(input_path).exists():
        raise HTTPException(
            status_code=422,
            detail=f"File not found (input_path): {input_path}",
        )
    if not Path(course_path).exists():
        raise HTTPException(
            status_code=422,
            detail=f"File not found (course_path): {course_path}",
        )
    if sales_pitch_path and not Path(sales_pitch_path).exists():
        raise HTTPException(
            status_code=422,
            detail=f"File not found (sales_pitch_path): {sales_pitch_path}",
        )

    # Resolve model: form field → env var → hard fallback
    resolved_model = (
        model
        or os.environ.get("OPENROUTER_DEFAULT_MODEL", "").strip()
        or "google/gemma-3-27b-it"
    )

    # --- Create pipeline job ---
    stt_job_id: str | None = None

    if audio_path:
        # Strip query params before extracting extension (GCS signed URLs have them).
        suffix = Path(audio_path.split("?")[0]).suffix.lower()
        if suffix not in _AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported audio format: {suffix}",
            )

        stt_job = SttJob(audio_path=audio_path, status="PENDING")
        db.add(stt_job)
        db.commit()
        db.refresh(stt_job)

        try:
            operation_name, gcs_uri = stt_service.submit_stt(audio_path)
        except (ValueError, RuntimeError) as exc:
            stt_job.status = "FAILED"
            stt_job.error = str(exc)
            db.commit()
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        stt_job.operation_name = operation_name
        stt_job.gcs_uri = gcs_uri
        stt_job.status = "SUBMITTED"
        db.commit()
        stt_job_id = stt_job.id

    pipeline_job = PipelineJob(
        stt_job_id=stt_job_id,
        input_path=input_path,
        course_path=course_path,
        sales_pitch_path=sales_pitch_path,
        model=resolved_model,
        rep_id=rep_id,
        call_id=call_id,
        sales_rep_name=sales_rep_name,
        customer_name=customer_name,
        current_step="STT_SUBMITTED" if stt_job_id else "PENDING",
        status="STT_SUBMITTED" if stt_job_id else "PENDING",
    )
    db.add(pipeline_job)
    db.commit()
    db.refresh(pipeline_job)

    # --- Directory creation & cleanup ---
    cleanup_empty_job_folders()
    job_out_dir = Path(__file__).resolve().parents[3] / "data" / "output" / pipeline_job.id
    (job_out_dir / "report").mkdir(parents=True, exist_ok=True)
    (job_out_dir / "transcript").mkdir(parents=True, exist_ok=True)
    (job_out_dir / "stt_result").mkdir(parents=True, exist_ok=True)

    # Launch the background task. FastAPI runs this after the response is sent.
    background_tasks.add_task(_run_pipeline, pipeline_job.id)

    return PipelineSubmitResponse(
        pipeline_id=pipeline_job.id,
        status=pipeline_job.status,
        message=(
            "Pipeline started. STT submitted to the configured provider. "
            "Poll /api/pipeline/status/{pipeline_id} for progress."
            if stt_job_id else
            "Pipeline started. Transcript input — skipping STT. "
            "Poll /api/pipeline/status/{pipeline_id} for progress."
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/pipeline/status/{pipeline_id}
# ---------------------------------------------------------------------------

@router.get("/status/{pipeline_id}", response_model=PipelineJobStatus)
def get_pipeline_status(
    pipeline_id: str,
    db: Session = Depends(get_db),
) -> PipelineJobStatus:
    """Return the current step and status of a pipeline run."""
    job = _get_pipeline_or_404(pipeline_id, db)

    return PipelineJobStatus(
        pipeline_id=job.id,
        status=job.status,
        current_step=job.current_step,
        stt_job_id=job.stt_job_id,
        input_path=job.input_path,
        course_path=job.course_path,
        sales_pitch_path=job.sales_pitch_path,
        model=job.model,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        sales_rep_name=job.sales_rep_name,
        customer_name=job.customer_name,
    )


# ---------------------------------------------------------------------------
# GET /api/pipeline/result/{pipeline_id}
# ---------------------------------------------------------------------------

@router.get("/result/{pipeline_id}", response_model=PipelineResultResponse)
def get_pipeline_result(
    pipeline_id: str,
    db: Session = Depends(get_db),
) -> PipelineResultResponse:
    """
    Fetch output file paths for a completed pipeline run.

    Returns 409 Conflict if the pipeline has not yet reached DONE status.
    """
    job = _get_pipeline_or_404(pipeline_id, db)

    if job.status == "FAILED":
        return PipelineResultResponse(
            pipeline_id=job.id,
            status=job.status,
            error=job.error,
        )

    if job.status != "DONE":
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline is not complete yet. Current step: {job.current_step}",
        )

    return PipelineResultResponse(
        pipeline_id=job.id,
        status=job.status,
        report_json_path=job.report_json_path,
        report_html_path=job.report_html_path,
        cleaned_vtt_path=job.cleaned_vtt_path,
        total_score=job.total_score,
        compliance_score=job.compliance_score,
        methodology_score=job.methodology_score,
        call_type=job.call_type,
        trust_stage=job.trust_stage,
        low_confidence=job.low_confidence,
        methodology_status=job.methodology_status,
        rubric_version=job.rubric_version,
        scoring_version=job.scoring_version,
    )


# ---------------------------------------------------------------------------
# Resume function — called at app startup
# ---------------------------------------------------------------------------

def resume_stuck_pipelines() -> None:
    """
    On startup, find any pipeline jobs stuck in a non-terminal state and
    restart their background tasks. This handles server restarts mid-pipeline.

    Called from main.py lifespan handler. Does NOT use FastAPI BackgroundTasks
    (which requires a live request). Instead it uses threading.Thread directly.
    """
    import threading

    db = new_session()
    try:
        stuck_statuses = ("PENDING", "STT_SUBMITTED", "STT_POLLING", "CLEANING", "ANALYZING", "REPORT_GEN")
        stuck_jobs = (
            db.query(PipelineJob)
            .filter(PipelineJob.status.in_(stuck_statuses))
            .all()
        )
        job_ids = [job.id for job in stuck_jobs]
    finally:
        db.close()

    for job_id in job_ids:
        thread = threading.Thread(target=_run_pipeline, args=(job_id,), daemon=True)
        thread.start()

    if job_ids:
        print(f"[startup] Resumed {len(job_ids)} stuck pipeline job(s): {job_ids}")