"""
Pydantic v2 schemas for all API request and response bodies.

Naming convention:
  <Resource>Submit   — POST request body
  <Resource>Status   — GET status response
  <Resource>Result   — GET result response (includes output paths/data)
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

class SttSubmitRequest(BaseModel):
    """Body for POST /api/stt/submit when sending a server-local file path."""
    audio_path: str = Field(..., description="Absolute or project-relative path to the audio file.")


class SttJobStatus(BaseModel):
    """Response for GET /api/stt/status/{job_id}."""
    job_id: str
    status: str = Field(..., description="PENDING | SUBMITTED | PROCESSING | DONE | FAILED | EXPIRED")
    operation_name: Optional[str] = None
    audio_path: str
    transcript_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SttSubmitResponse(BaseModel):
    """Response for POST /api/stt/submit."""
    job_id: str
    status: str
    operation_name: Optional[str] = None
    message: str


class SttResultResponse(BaseModel):
    """Response for GET /api/stt/result/{job_id}."""
    job_id: str
    status: str
    transcript_path: Optional[str] = None
    utterances: Optional[list[dict]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class PipelineSubmitRequest(BaseModel):
    """
    Body for POST /api/pipeline/submit.

    Exactly one of audio_path or transcript_path must be provided.
    - audio_path   → pipeline runs STT first, then clean → analyze → report.
    - transcript_path → pipeline skips STT, starts at clean step.
    """
    audio_path: Optional[str] = Field(
        None,
        description="Path to audio file. Triggers STT before cleaning."
    )
    transcript_path: Optional[str] = Field(
        None,
        description="Path to existing transcript (.srt/.vtt/.json/.txt). Skips STT."
    )
    course_path: str = Field(
        ...,
        description="Path to the course-offering CSV file."
    )
    sales_pitch_path: Optional[str] = Field(
        None,
        description="Path to dynamic sales pitch .md file."
    )
    model: str = Field(
        "anthropic/claude-3-5-sonnet",
        description="OpenRouter model identifier."
    )
    rep_id: Optional[str] = Field(None, description="Sales rep email or employee ID.")
    call_id: Optional[str] = Field(None, description="CRM call ID.")
    sales_rep_name: Optional[str] = Field(None, description="Expected sales rep name.")
    customer_name: Optional[str] = Field(None, description="Expected customer name.")


class PipelineJobStatus(BaseModel):
    """Response for GET /api/pipeline/status/{pipeline_id}."""
    pipeline_id: str
    status: str = Field(
        ...,
        description="PENDING | STT_SUBMITTED | STT_POLLING | CLEANING | ANALYZING | REPORT_GEN | DONE | FAILED"
    )
    current_step: str
    stt_job_id: Optional[str] = None
    input_path: str
    course_path: str
    sales_pitch_path: Optional[str] = None
    model: str
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    sales_rep_name: Optional[str] = None
    customer_name: Optional[str] = None


class PipelineSubmitResponse(BaseModel):
    """Response for POST /api/pipeline/submit."""
    pipeline_id: str
    status: str
    message: str


class PipelineResultResponse(BaseModel):
    """Response for GET /api/pipeline/result/{pipeline_id}."""
    pipeline_id: str
    status: str
    report_json_path: Optional[str] = None
    report_html_path: Optional[str] = None
    cleaned_vtt_path: Optional[str] = None
    error: Optional[str] = None

    # --- Scoring ---
    # All optional with defaults, so existing clients are unaffected and rows
    # created before this feature return nulls rather than erroring.
    total_score: Optional[int] = Field(
        None,
        description="Overall call score, 0-100. Null if the methodology pass failed."
    )
    compliance_score: Optional[float] = Field(
        None, description="Fact-check component of the total score."
    )
    methodology_score: Optional[float] = Field(
        None, description="Sales Bible adherence component of the total score."
    )
    call_type: Optional[str] = Field(
        None,
        description=(
            "discovery | full_pitch | follow_up | closing | transactional. "
            "Compare scores within a call type, not across types — a short "
            "discovery call is judged on fewer rubric dimensions."
        )
    )
    trust_stage: Optional[str] = Field(
        None,
        description="Furthest TRUST Journey stage reached: hear_me | "
                    "understand_me | guide_me | reassure_me | i_ll_decide."
    )
    low_confidence: Optional[bool] = Field(
        None,
        description="True when the call was too short or one-sided for a "
                    "reliable methodology read. Review manually."
    )
    methodology_status: Optional[str] = Field(
        None, description="ok | failed. 'failed' means compliance-only results."
    )
    rubric_version: Optional[str] = None
    scoring_version: Optional[str] = None


# ---------------------------------------------------------------------------
# Clean (synchronous utility)
# ---------------------------------------------------------------------------

class CleanRequest(BaseModel):
    """Body for POST /api/clean."""
    transcript_path: str = Field(
        ...,
        description="Path to transcript file (.json/.srt/.vtt/.txt)."
    )
    rep_speaker: Optional[str] = Field(
        None,
        description="Override speaker label to use as SALES_REP. Defaults to first speaker."
    )
    customer_name: Optional[str] = Field(
        None,
        description="Expected customer name. Replaces the derived customer name in the VTT file if it doesn't match."
    )


class CleanResponse(BaseModel):
    """Response for POST /api/clean."""
    cleaned_vtt_path: str
    stats: dict[str, Any]


# ---------------------------------------------------------------------------
# Analyze (synchronous utility — calls OpenRouter directly)
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """Body for POST /api/analyze."""
    cleaned_vtt_path: str = Field(..., description="Path to cleaned transcript VTT file.")
    course_path: str = Field(..., description="Path to course-offering CSV.")
    sales_pitch_path: Optional[str] = None
    model: str = Field(
        "anthropic/claude-3-5-sonnet",
        description="OpenRouter model identifier."
    )
    call_id: Optional[str] = None
    call_recording_file: Optional[str] = None
    call_stt_file: Optional[str] = None
    sales_rep_name: Optional[str] = None
    sales_rep_id: Optional[str] = None
    customer_name: Optional[str] = None
    call_duration: Optional[str] = None
    no_of_words: Optional[int] = None
    stats: Optional[dict[str, Any]] = Field(
        None,
        description="Stats dict from the cleaning step (duration, words, tokens, etc.)."
    )


class AnalyzeResponse(BaseModel):
    """Response for POST /api/analyze."""
    report_json_path: str
    model_used: str
    tokens_utilized: int


# ---------------------------------------------------------------------------
# Report HTML (synchronous utility)
# ---------------------------------------------------------------------------

class ReportHtmlRequest(BaseModel):
    """Body for POST /api/report/html."""
    report_json_path: str = Field(..., description="Path to the .report.json file.")


class ReportHtmlResponse(BaseModel):
    """Response for POST /api/report/html."""
    report_html_path: str


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str