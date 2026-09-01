"""
Cleaning service — wraps src/clean.py for use inside the FastAPI pipeline.

run_clean() accepts a transcript file path (JSON/SRT/VTT/TXT), runs the
full cleaning pipeline (speaker labeling, term corrections, filler removal),
writes output/<stem>.cleaned.vtt, and returns
a stats dict that the pipeline stores and the analysis service consumes.

This is a synchronous function. Call it from a FastAPI background task or
wrap with anyio.to_thread.run_sync() when needed inside async code.
"""

import os
import sys
from pathlib import Path
from typing import Any
from src.metrics.conversational import parse_utterances, compute_metrics  # noqa: E402

# Resolve project root so we can import clean.py without installing the package.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.clean import (  # noqa: E402
    load_json_transcript,
    load_srt_transcript,
    load_vtt_transcript,
    load_text_transcript,
    label_speakers,
    apply_corrections,
    strip_fillers,
    format_cleaned_vtt,
    compute_stats,
    load_corrections,
    DEFAULT_REP_SPEAKER,
)


def run_clean(
    pipeline_id: str,
    transcript_path: str,
    rep_speaker: str | int | None = None,
    customer_name: str | None = None,
    sales_rep_name: str | None = None,
) -> dict[str, Any]:
    """
    Clean a transcript file and write output files.

    Args:
        transcript_path: Path to the source transcript (.json/.srt/.vtt/.txt).
        rep_speaker:     Override the speaker tag to label as SALES_REP.
                         If None, defaults to the first speaker in the file.

    Returns a dict with:
        cleaned_vtt_path  — path to output/<stem>.cleaned.vtt
        stats             — call statistics (duration, words, tokens, names, etc.)
    """
    path = Path(transcript_path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript not found: {transcript_path}")

    suffix = path.suffix.lower()

    if suffix == ".json":
        utterances = load_json_transcript(path)
        if rep_speaker is not None:
            try:
                effective_rep = int(rep_speaker)
            except (ValueError, TypeError):
                effective_rep = rep_speaker
        else:
            effective_rep = DEFAULT_REP_SPEAKER
    elif suffix in (".txt", ".text"):
        utterances = load_text_transcript(path)
        effective_rep = rep_speaker or (utterances[0]["speaker"] if utterances else "Speaker 1")
    elif suffix == ".srt":
        utterances = load_srt_transcript(path)
        effective_rep = rep_speaker or (utterances[0]["speaker"] if utterances else "Speaker 1")
    elif suffix == ".vtt":
        utterances = load_vtt_transcript(path)
        effective_rep = rep_speaker or (utterances[0]["speaker"] if utterances else "Speaker 1")
    else:
        raise ValueError(
            f"Unsupported transcript format: {suffix}. "
            "Expected .json, .txt, .text, .srt, or .vtt"
        )

    corrections = load_corrections()
    fillers = corrections.get("filler_words", [])

    utterances = label_speakers(utterances, effective_rep, customer_name=customer_name)

    for utt in utterances:
        utt["text"] = apply_corrections(utt["text"], corrections)
        utt["text"] = strip_fillers(utt["text"], fillers)

    formatted_vtt = format_cleaned_vtt(utterances)

    output_dir = _PROJECT_ROOT / "data" / "output" / pipeline_id / "transcript"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Strip our own .transcript suffix if it was produced by transcribe.py.
    stem = path.stem.replace(".transcript", "")

    out_vtt = output_dir / f"{stem}.cleaned.vtt"

    out_vtt.write_text(formatted_vtt, encoding="utf-8")

    # Derive speaker names for stats.
    rep_name = next(
        (u["speaker"] for u in utterances if u.get("role") == "SALES_REP" and u.get("speaker")),
        "Unknown",
    )
    extracted_customer_name = next(
        (u["speaker"] for u in utterances if u.get("role") == "CUSTOMER" and u.get("speaker")),
        "Unknown",
    )

    # If an expected sales_rep_name was provided, check if it matches the extracted one.
    if sales_rep_name:
        if rep_name == "Unknown" or sales_rep_name.lower() != rep_name.lower():
            for u in utterances:
                if u.get("role") == "SALES_REP":
                    u["speaker"] = sales_rep_name
            
            if suffix == ".vtt" and rep_name != "Unknown":
                try:
                    vtt_text = path.read_text(encoding="utf-8")
                    import re
                    vtt_text = re.sub(
                        rf"\[{re.escape(rep_name)}\]:", 
                        f"[{sales_rep_name}]:", 
                        vtt_text,
                        flags=re.IGNORECASE
                    )
                    path.write_text(vtt_text, encoding="utf-8")
                except Exception as e:
                    print(f"Warning: Failed to rewrite VTT file with updated sales rep name: {e}")
                    
            rep_name = sales_rep_name

    # If an expected customer_name was provided, check if it matches the extracted one.
    if customer_name:
        if extracted_customer_name == "Unknown" or customer_name.lower() != extracted_customer_name.lower():
            # Update the speaker label in utterances
            for u in utterances:
                if u.get("role") == "CUSTOMER":
                    u["speaker"] = customer_name
            
            # Rewrite the original transcript file if it was a VTT file to replace the name
            if suffix == ".vtt" and extracted_customer_name != "Unknown":
                try:
                    vtt_text = path.read_text(encoding="utf-8")
                    # Safely replace [Extracted Name]: with [Expected Name]:
                    import re
                    vtt_text = re.sub(
                        rf"\[{re.escape(extracted_customer_name)}\]:", 
                        f"[{customer_name}]:", 
                        vtt_text,
                        flags=re.IGNORECASE
                    )
                    path.write_text(vtt_text, encoding="utf-8")
                except Exception as e:
                    print(f"Warning: Failed to rewrite VTT file with updated customer name: {e}")
                    
            extracted_customer_name = customer_name

    # format_cleaned_vtt doesn't provide a flat text for compute_stats like format_transcript did,
    # but compute_stats only needs utterances, not the formatted text anyway.
    stats = compute_stats(utterances, "")
    stats["sales_rep_name"] = rep_name
    stats["customer_name"] = extracted_customer_name
    stats["stt_file"] = str(transcript_path)
    stats["rep_utterances"] = sum(1 for u in utterances if u.get("role") == "SALES_REP")
    stats["customer_utterances"] = sum(1 for u in utterances if u.get("role") == "CUSTOMER")

    # Metrics are computed here, not from the VTT, because `utterances` already
    # carries authoritative role tags. Re-parsing the rendered VTT would depend
    # on however format_cleaned_vtt() happens to label speakers.
    turns = parse_utterances(utterances)
    metrics = compute_metrics(turns, customer_name=extracted_customer_name)

    return {
        "cleaned_vtt_path": str(out_vtt),
        "stats": stats,
        "metrics": metrics,
    }
