"""
Report generation service — wraps src/report_html.py for use inside the
FastAPI pipeline.

run_report_html() accepts a report JSON path, generates the HTML file in the
same output/ directory, and returns the HTML file path.

This is a synchronous function intended for use in background tasks.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.report_html import generate_html  # noqa: E402


def run_report_html(pipeline_id: str, report_json_path: str) -> str:
    """
    Generate an HTML report from a report JSON file.

    Args:
        report_json_path: Absolute path to the .report.json file.

    Returns:
        Absolute path to the written .report.html file.
    """
    import json

    json_path = Path(report_json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"Report JSON not found: {report_json_path}")

    with json_path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    html = generate_html(data)

    # Place the HTML alongside the JSON.
    stem = json_path.stem  # e.g. "0.report"
    if not stem.endswith(".report"):
        stem = stem + ".report"
    html_path = json_path.parent / f"{stem}.html"

    html_path.write_text(html, encoding="utf-8")
    return str(html_path)
