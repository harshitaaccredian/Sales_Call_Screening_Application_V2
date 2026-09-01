"""
Report route — POST /api/report/html

Synchronous utility endpoint. Accepts a .report.json path via form data and
generates an HTML report. Returns the HTML file path.
"""

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException

from src.api.models.schemas import ReportHtmlResponse
from src.api.services.report_service import run_report_html

router = APIRouter(prefix="/api/report", tags=["Report"])


@router.post("/html", response_model=ReportHtmlResponse)
def generate_html_report(
    report_json_path: str = Form(..., description="Path to the .report.json file."),
) -> ReportHtmlResponse:
    """
    Generate an HTML report from an existing report JSON file.

    Send as **form data** (`Content-Type: application/x-www-form-urlencoded`).
    """
    report_json_path = report_json_path.replace("\\", "/")

    if not Path(report_json_path).exists():
        raise HTTPException(
            status_code=422,
            detail=f"Report JSON not found: {report_json_path}",
        )

    try:
        html_path = run_report_html(report_json_path=report_json_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ReportHtmlResponse(report_html_path=html_path)
