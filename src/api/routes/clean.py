"""
Clean route — POST /api/clean

Synchronous utility endpoint. Accepts a transcript file path via form data
and runs the full cleaning pipeline (speaker labeling, term corrections,
filler removal). Returns paths to the cleaned files and call statistics.
"""

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException

from src.api.models.schemas import CleanResponse
from src.api.services.clean_service import run_clean

router = APIRouter(prefix="/api/clean", tags=["Clean"])


@router.post("", response_model=CleanResponse)
def clean_transcript(
    transcript_path: str = Form(
        ...,
        description="Server-local path to transcript (.json/.srt/.vtt/.txt). Forward or back slashes accepted.",
    ),
    rep_speaker: str | None = Form(
        None,
        description="Override speaker label to treat as SALES_REP. Defaults to first speaker.",
    ),
    customer_name: str | None = Form(
        None,
        description="Expected customer name. Replaces the derived customer name in the VTT file if it doesn't match.",
    ),
) -> CleanResponse:
    """
    Clean a transcript file and return the output paths + call statistics.

    Send as **form data** (`Content-Type: application/x-www-form-urlencoded`).
    Supported transcript formats: .json, .srt, .vtt, .txt / .text
    """
    transcript_path = transcript_path.replace("\\", "/")

    if not Path(transcript_path).exists():
        raise HTTPException(
            status_code=422,
            detail=f"Transcript file not found: {transcript_path}",
        )

    try:
        result = run_clean(
            pipeline_id="api_clean", # arbitrary pipeline_id for direct clean calls
            transcript_path=transcript_path, 
            rep_speaker=rep_speaker,
            customer_name=customer_name
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return CleanResponse(
        cleaned_vtt_path=result["cleaned_vtt_path"],
        stats=result["stats"],
    )
