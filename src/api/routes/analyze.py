"""
Analyze route — POST /api/analyze

Synchronous utility endpoint. Accepts paths via form data and calls OpenRouter
to perform QA analysis on a cleaned transcript. Returns the report JSON path.

Note: This blocks until the LLM call completes (30–90 s for long transcripts).
Use /api/pipeline/submit for true async handling.
"""

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException

from src.api.models.schemas import AnalyzeResponse
from src.api.services.analysis_service import run_analysis
import os

DEFAULT_MODEL = os.getenv("OPENROUTER_DEFAULT_MODEL")

router = APIRouter(prefix="/api/analyze", tags=["Analyze"])


@router.post("", response_model=AnalyzeResponse)
def analyze_transcript(
    cleaned_txt_path: str = Form(..., description="Path to cleaned transcript .txt file."),
    course_path: str = Form(..., description="Path to course-offering CSV."),
    sales_pitch_path: str | None = Form(None, description="Path to dynamic sales pitch .md file."),
    model: str = Form(DEFAULT_MODEL, description="OpenRouter model identifier."),
    call_id: str | None = Form(None),
    call_recording_file: str | None = Form(None),
    call_stt_file: str | None = Form(None),
    sales_rep_name: str | None = Form(None),
    sales_rep_id: str | None = Form(None),
    customer_name: str | None = Form(None),
    call_duration: str | None = Form(None),
    no_of_words: int | None = Form(None),
) -> AnalyzeResponse:
    """
    Run QA analysis on a cleaned transcript via OpenRouter.

    Send as **form data** (`Content-Type: application/x-www-form-urlencoded`).
    Returns the path to the generated .report.json file.
    """
    cleaned_txt_path = cleaned_txt_path.replace("\\", "/")
    course_path = course_path.replace("\\", "/")
    if sales_pitch_path:
        sales_pitch_path = sales_pitch_path.replace("\\", "/")

    paths_to_check = [
        ("cleaned_txt_path", cleaned_txt_path),
        ("course_path", course_path),
    ]
    if sales_pitch_path:
        paths_to_check.append(("sales_pitch_path", sales_pitch_path))

    for label, path_str in paths_to_check:
        if not Path(path_str).exists():
            raise HTTPException(
                status_code=422,
                detail=f"File not found ({label}): {path_str}",
            )

    try:
        result = run_analysis(
            pipeline_id="sync_analysis",
            cleaned_vtt_path=cleaned_txt_path,
            course_path=course_path,
            sales_pitch_path=sales_pitch_path,
            model=model,
            call_id=call_id,
            call_recording_file=call_recording_file,
            call_stt_file=call_stt_file,
            sales_rep_name=sales_rep_name,
            sales_rep_id=sales_rep_id,
            customer_name=customer_name,
            call_duration=call_duration,
            no_of_words=no_of_words,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return AnalyzeResponse(
        report_json_path=result["report_json_path"],
        model_used=result["model_used"],
        tokens_utilized=result["tokens_utilized"],
    )
