"""
Assessment service — orchestrates the two analysis passes and merges the result.

This is the single entry point the pipeline route should call instead of
run_analysis() directly.

  ┌─ analysis_service.run_analysis()      (LLM call A — compliance)
  ├─ methodology_service.run_methodology() (LLM call B — Sales Bible)
  └─ scoring.compute_overall_score()       (Python — deterministic)

Both LLM calls are blocking, network-bound and share no state, so they run
concurrently in a ThreadPoolExecutor. Wall-clock is max(A, B), not A + B.

Degradation policy: if call B fails, the compliance report is still written
and returned with `methodology_status: "failed"`. Fact-checking works today
and must not be taken down by the newer, less-proven pass. If call A fails,
the whole job fails — there is no useful report without it.

Scope: this service writes ONLY `report.rubric_assessment`. It never touches
`report.overall_call_score` or `report.sales_pitch_coverage`, which belong to
the sales-pitch scoring feature and render in their own section when a Sales
Pitch is uploaded. Two independent scores, deliberately not blended.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.api.services.analysis_service import run_analysis          # noqa: E402
from src.api.services.methodology_service import run_methodology    # noqa: E402
from src.scoring import compute_overall_score                       # noqa: E402


def run_assessment(
    pipeline_id: str,
    cleaned_vtt_path: str,
    course_path: str,
    model: str,
    metrics: dict,
    sales_pitch_path: str | None = None,
    methodology_model: str | None = None,
    *,
    call_id: str | None = None,
    call_recording_file: str | None = None,
    call_stt_file: str | None = None,
    sales_rep_name: str | None = None,
    sales_rep_id: str | None = None,
    customer_name: str | None = None,
    call_duration: str | None = None,
    no_of_words: int | None = None,
    stats: dict | None = None,
) -> dict[str, Any]:
    """
    Run compliance and methodology assessment in parallel, then score.

    Args:
        metrics:            output of compute_metrics(), from clean_service.
        methodology_model:  optional separate model for call B. Defaults to
                            `model`. Useful if you want a cheaper tier for the
                            judgement pass, which is less precision-critical
                            than digit-level fact-checking.

    Returns the same shape as run_analysis(), plus methodology fields.
    """
    meth_model = methodology_model or model

    with ThreadPoolExecutor(max_workers=2) as executor:
        fut_analysis = executor.submit(
            run_analysis,
            pipeline_id=pipeline_id,
            cleaned_vtt_path=cleaned_vtt_path,
            course_path=course_path,
            model=model,
            sales_pitch_path=sales_pitch_path,
            call_id=call_id,
            call_recording_file=call_recording_file,
            call_stt_file=call_stt_file,
            sales_rep_name=sales_rep_name,
            sales_rep_id=sales_rep_id,
            customer_name=customer_name,
            call_duration=call_duration,
            no_of_words=no_of_words,
            stats=stats,
        )
        fut_methodology = executor.submit(
            run_methodology,
            pipeline_id=pipeline_id,
            cleaned_vtt_path=cleaned_vtt_path,
            model=meth_model,
            metrics=metrics,
            sales_pitch_path=sales_pitch_path,
        )

        # Call A first — if it raises, the job is dead regardless of B.
        analysis_result = fut_analysis.result()

        methodology_result: dict | None = None
        methodology_error: str | None = None
        methodology_tokens = 0
        try:
            m = fut_methodology.result()
            methodology_result = m["methodology"]
            methodology_tokens = m["tokens_utilized"]
        except Exception as exc:  # noqa: BLE001 — degrade, never fail the job
            methodology_error = str(exc)

    # ---- Merge into the report JSON that report_service will read ----
    report_path = Path(analysis_result["report_json_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    node = report.setdefault("report", {})

    if methodology_result is not None:
        score = compute_overall_score(
            compliance_result=report,
            methodology_result=methodology_result,
            metrics=metrics,
        )
        score["coaching_summary"] = methodology_result.get("coaching_summary")
        # Carry the deterministic metrics on the score object so the Call
        # Overview can render them without changing render_methodology_section's
        # signature (and therefore report_html.py).
        score["_metrics"] = metrics
        score["executive_summary"] = methodology_result.get("executive_summary")

        # IMPORTANT: writes to `rubric_assessment`, never `overall_call_score`.
        # `overall_call_score` and `sales_pitch_coverage` are produced by
        # analysis_prompt.md when a Sales Pitch is uploaded, and drive the
        # pre-existing pitch-score section. Overwriting either would delete a
        # working feature.
        node["rubric_assessment"] = score
        node["methodology"] = methodology_result
        node["conversation_metrics"] = metrics
        report["methodology_status"] = "ok"
        report["call_type"] = methodology_result.get("call_type")
        report["total_score"] = score["total_score"]
        report["rubric_version"] = score["rubric_version"]
        report["scoring_version"] = score["scoring_version"]
        report["trust_stage"] = (
            methodology_result.get("trust_journey", {}).get("furthest_stage_reached")
        )
        report["low_confidence"] = score["low_confidence"]
    else:
        # Compliance-only report. Explicit null beats a partial score that
        # looks authoritative but was computed from half the inputs.
        # `overall_call_score` is left exactly as analysis_service wrote it.
        node["rubric_assessment"] = None
        node["conversation_metrics"] = metrics
        report["methodology_status"] = "failed"
        report["methodology_error"] = methodology_error

    total_tokens = (analysis_result.get("tokens_utilized") or 0) + methodology_tokens
    report["tokens_utilized"] = total_tokens
    if "call_statistics" in node:
        node["call_statistics"]["total_tokens"] = total_tokens

    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        **analysis_result,
        "tokens_utilized": total_tokens,
        "methodology_status": report["methodology_status"],
        "methodology_error": methodology_error,
        "total_score": report.get("total_score"),
        "call_type": report.get("call_type"),
        "trust_stage": report.get("trust_stage"),
        "low_confidence": report.get("low_confidence"),
        "rubric_version": report.get("rubric_version"),
        "scoring_version": report.get("scoring_version"),
    }