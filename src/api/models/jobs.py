"""
ORM models for job persistence.

SttJob   — tracks a single Google Cloud STT operation (one audio file).
PipelineJob — tracks the full call-quality pipeline run from input to report.

Both tables use UUID primary keys (stored as TEXT in SQLite) so IDs are safe
to expose in API responses and URLs without leaking sequential enumeration.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class SttJob(Base):
    """
    Represents one Google Cloud Speech-to-Text long-running operation.

    Lifecycle:
      PENDING       — job created, STT not yet submitted (rare transient state)
      SUBMITTED     — long_running_recognize called, operation_name stored
      PROCESSING    — Google is still transcribing
      DONE          — transcription complete, transcript_path populated
      FAILED        — Google returned an error or we hit a timeout
      EXPIRED       — operation_name no longer exists on Google's side (>14 days)
    """

    __tablename__ = "stt_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)

    # The full operation name returned by Google, e.g.
    # "projects/my-project/locations/global/operations/1234567890"
    # Null until submit_stt() has been called.
    operation_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # GCS URI where the converted FLAC was staged before submission, e.g.
    # "gs://my-bucket/stt-uploads/abc123.flac". Stored so it can be deleted
    # once transcription is complete and we no longer need the staged file.
    gcs_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Path to the source audio file on disk.
    audio_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Populated once transcription is done.
    transcript_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )

    # Error message when status == FAILED.
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    # Back-reference to pipeline jobs that use this STT job.
    pipeline_jobs: Mapped[list["PipelineJob"]] = relationship(
        "PipelineJob", back_populates="stt_job"
    )

    def __repr__(self) -> str:
        return f"<SttJob id={self.id} status={self.status}>"


class PipelineJob(Base):
    """
    Represents one full call-quality pipeline run.

    Pipeline steps (reflected in current_step):
      STT_SUBMITTED  — audio submitted to Google STT (only when input is audio)
      STT_POLLING    — polling Google for STT completion
      CLEANING       — running clean.py on the transcript/SRT/VTT
      ANALYZING      — compliance + methodology LLM calls in parallel,
                       then deterministic scoring (src/scoring.py)
      REPORT_GEN     — generating HTML report
      DONE           — pipeline complete, all output files populated
      FAILED         — unrecoverable error, see error field

    Input modes:
      - audio: stt_job_id is set; pipeline waits for STT before cleaning.
      - srt/vtt/json/txt: stt_job_id is null; pipeline starts at CLEANING.
    """

    __tablename__ = "pipeline_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)

    # Foreign key to SttJob — null when input is already a transcript.
    stt_job_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("stt_jobs.id"), nullable=True
    )
    stt_job: Mapped[Optional[SttJob]] = relationship(
        "SttJob", back_populates="pipeline_jobs"
    )

    # Input file path — audio file OR transcript file (SRT/VTT/JSON/TXT).
    input_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Path to the course CSV used for analysis.
    course_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional path to the dynamic sales pitch markdown file.
    sales_pitch_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # OpenRouter model identifier, e.g. "anthropic/claude-3-5-sonnet".
    model: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional metadata passed through to the report.
    rep_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    call_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sales_rep_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Current pipeline step (matches the lifecycle states above).
    current_step: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )

    # Overall status — mirrors current_step but stays FAILED/DONE at end.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )

    # Populated progressively as each step completes.
    cleaned_vtt_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_json_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_html_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Scoring (written by assessment_service during the ANALYZING step) ---
    # All nullable: a run that fails before analysis, or one where the
    # methodology pass fails, legitimately has no score.
    total_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    compliance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    methodology_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # discovery | full_pitch | follow_up | closing | transactional.
    # Scores are only comparable WITHIN a call type — a short discovery call is
    # judged on fewer rubric dimensions, so it has fewer places to lose points.
    call_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Furthest TRUST Journey stage reached.
    trust_stage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    low_confidence: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # ok | failed — the compliance report still writes when the methodology
    # pass fails, with a null score.
    methodology_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Stamped on every row so scores stay comparable as the Bible and the
    # weights are revised. Without these, a trend chart built six months from
    # now is silently wrong with no way to detect it after the fact.
    rubric_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scoring_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Error message when status == FAILED.
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    def __repr__(self) -> str:
        return f"<PipelineJob id={self.id} step={self.current_step} status={self.status}>"