# """
# Methodology service — calls OpenRouter to assess a cleaned call transcript
# against the Accredian Sales Bible rubric.

# This is LLM call B. It runs in PARALLEL with analysis_service (call A) and
# shares no state with it. Deliberately separate so that a malformed methodology
# response cannot take down fact-checking, which already works.

# Flow:
#   1. Load system prompt from config/methodology_prompt.md.
#   2. Build user message: cleaned transcript + rubric + deterministic metrics.
#   3. Call OpenRouter (OpenAI-compatible endpoint).
#   4. Parse and validate JSON.
#   5. Save to output/<pipeline_id>/report/<stem>.methodology.json.

# The model assigns BANDS and supplies EVIDENCE. It never computes a score —
# all arithmetic happens in src/scoring.py.
# """

# import json
# import os
# import sys
# from pathlib import Path
# from typing import Any

# from dotenv import load_dotenv

# load_dotenv()

# _PROJECT_ROOT = Path(__file__).resolve().parents[3]
# if str(_PROJECT_ROOT) not in sys.path:
#     sys.path.insert(0, str(_PROJECT_ROOT))

# _METHODOLOGY_PROMPT_PATH = _PROJECT_ROOT / "config" / "methodology_prompt.md"
# _RUBRIC_PATH = _PROJECT_ROOT / "config" / "sales_bible_rubric.yaml"

# # Required dimension ids — used to validate the response before it reaches
# # the scorer, so a truncated generation fails loudly here rather than
# # silently producing a high score from missing dimensions.
# _REQUIRED_DIMENSIONS = {
#     "customer_profiling", "need_identification", "vision_setting",
#     "program_mapping", "fee_and_urgency", "objection_handling", "trust_journey",
# }


# def _load_system_prompt() -> str:
#     if not _METHODOLOGY_PROMPT_PATH.exists():
#         raise FileNotFoundError(f"Methodology prompt not found: {_METHODOLOGY_PROMPT_PATH}")
#     return _METHODOLOGY_PROMPT_PATH.read_text(encoding="utf-8")


# def _build_user_message(
#     cleaned_vtt_path: str,
#     metrics: dict,
#     sales_pitch_path: str | None = None,
# ) -> str:
#     transcript = Path(cleaned_vtt_path).read_text(encoding="utf-8", errors="replace")
#     rubric = _RUBRIC_PATH.read_text(encoding="utf-8")

#     # Strip the example blocks from metrics before sending — they duplicate
#     # transcript content the model already has and inflate input tokens.
#     slim = {k: v for k, v in metrics.items()
#             if not k.endswith("_examples")}

#     msg = (
#         "## Cleaned Transcript\n\n"
#         f"{transcript}\n\n"
#         "## Rubric\n\n"
#         f"{rubric}\n\n"
#         "## Conversation Metrics\n\n"
#         "These were computed programmatically from the transcript. They are "
#         "ground truth. Where they conflict with your impression, they win.\n\n"
#         "```json\n"
#         f"{json.dumps(slim, indent=2)}\n"
#         "```\n\n"
#     )

#     if sales_pitch_path and Path(sales_pitch_path).exists():
#         msg += "## Sales Pitch\n\n" + Path(sales_pitch_path).read_text(
#             encoding="utf-8", errors="replace") + "\n\n"

#     msg += (
#         "Assess the call against the rubric. Assign a band per dimension with "
#         "verbatim evidence. Return only the JSON object. Do not compute scores."
#     )
#     return msg


# def _call_openrouter(system_prompt: str, user_message: str, model: str) -> tuple[str, dict]:
#     """Call OpenRouter and return the raw text response and token usage."""
#     from openai import OpenAI

#     api_key = os.environ.get("OPENROUTER_API_KEY")
#     if not api_key:
#         raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to your .env file.")

#     client = OpenAI(
#         base_url="https://openrouter.ai/api/v1",
#         api_key=api_key,
#         default_headers={
#             "HTTP-Referer": "https://accredian.com",
#             "X-Title": "Accredian Call Quality Agent",
#         },
#     )

#     response = client.chat.completions.create(
#         model=model,
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": user_message},
#         ],
#         response_format={"type": "json_object"},
#         # 0.0, not 0.1. This is a judgement pass feeding a deterministic scorer;
#         # any sampling variance shows up directly as score drift between runs
#         # on the same call, which is the thing that destroys trust in a QA tool.
#         temperature=0.0,
#     )

#     usage = response.usage
#     return response.choices[0].message.content or "", {
#         "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
#         "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
#         "total_tokens": getattr(usage, "total_tokens", 0) if usage else 0,
#     }


# def _parse_json_response(raw: str) -> dict:
#     """Parse the LLM response, stripping markdown fences if present."""
#     text = raw.strip()
#     if text.startswith("```"):
#         lines = text.splitlines()
#         inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
#         text = "\n".join(inner).strip()
#     return json.loads(text)


# def _validate(result: dict) -> None:
#     """Fail loudly on a structurally incomplete response.

#     A truncated generation that drops three dimensions would otherwise be
#     scored as 'those stages did not occur' and inflate the methodology score.
#     """
#     dims = result.get("dimensions")
#     if not isinstance(dims, list):
#         raise ValueError("Methodology response missing 'dimensions' array")

#     got = {d.get("id") for d in dims if isinstance(d, dict)}
#     missing = _REQUIRED_DIMENSIONS - got
#     if missing:
#         raise ValueError(f"Methodology response missing dimensions: {sorted(missing)}")

#     valid_bands = {"not_applicable", "missing", "average", "good", "great", None}
#     for d in dims:
#         if d.get("band") not in valid_bands:
#             raise ValueError(f"Invalid band '{d.get('band')}' for dimension '{d.get('id')}'")


# def run_methodology(
#     pipeline_id: str,
#     cleaned_vtt_path: str,
#     model: str,
#     metrics: dict,
#     sales_pitch_path: str | None = None,
# ) -> dict[str, Any]:
#     """
#     Run Sales Bible methodology assessment on a cleaned transcript.

#     Args:
#         metrics: output of src.metrics.conversational.compute_metrics(),
#                  produced by clean_service. Passed to the model as ground truth.

#     Returns:
#         {
#           "methodology_json_path": str,
#           "methodology": dict,
#           "model_used": str,
#           "tokens_utilized": int,
#         }

#     Raises:
#         RuntimeError if the LLM fails to return valid JSON after two attempts.
#     """
#     system_prompt = _load_system_prompt()
#     user_message = _build_user_message(cleaned_vtt_path, metrics, sales_pitch_path)

#     raw, usage = _call_openrouter(system_prompt, user_message, model)

#     try:
#         result = _parse_json_response(raw)
#         _validate(result)
#     except (json.JSONDecodeError, ValueError) as first_error:
#         correction = (
#             f"Your previous response was rejected: {first_error}. "
#             "Return only the raw JSON object with all seven dimension ids present "
#             "— no markdown, no fences, no explanation."
#         )
#         raw, usage2 = _call_openrouter(system_prompt, user_message + "\n\n" + correction, model)
#         usage = {k: usage.get(k, 0) + usage2.get(k, 0) for k in usage2}
#         try:
#             result = _parse_json_response(raw)
#             _validate(result)
#         except (json.JSONDecodeError, ValueError) as exc:
#             stem = Path(cleaned_vtt_path).stem.replace(".cleaned", "")
#             output_dir = _PROJECT_ROOT / "data" / "output" / pipeline_id / "report"
#             output_dir.mkdir(parents=True, exist_ok=True)
#             raw_path = output_dir / f"{stem}.raw_methodology_response.txt"
#             raw_path.write_text(raw, encoding="utf-8")
#             raise RuntimeError(
#                 f"Methodology assessment returned invalid output after two attempts: {exc}. "
#                 f"Raw response saved to {raw_path}"
#             ) from exc

#     stem = Path(cleaned_vtt_path).stem.replace(".cleaned", "")
#     output_dir = _PROJECT_ROOT / "data" / "output" / pipeline_id / "report"
#     output_dir.mkdir(parents=True, exist_ok=True)
#     out_path = output_dir / f"{stem}.methodology.json"
#     out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

#     return {
#         "methodology_json_path": str(out_path),
#         "methodology": result,
#         "model_used": model,
#         "tokens_utilized": usage.get("total_tokens", 0),
#     }

"""
Methodology service — calls OpenRouter to assess a cleaned call transcript
against the Accredian Sales Bible rubric.

This is LLM call B. It runs in PARALLEL with analysis_service (call A) and
shares no state with it. Deliberately separate so that a malformed methodology
response cannot take down fact-checking, which already works.

Flow:
  1. Load system prompt from config/methodology_prompt.md.
  2. Build user message: cleaned transcript + rubric + deterministic metrics.
  3. Call OpenRouter (OpenAI-compatible endpoint).
  4. Parse and validate JSON.
  5. Save to output/<pipeline_id>/report/<stem>.methodology.json.

The model assigns BANDS and supplies EVIDENCE. It never computes a score —
all arithmetic happens in src/scoring.py.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Same reasoning as analysis_service: without an explicit ceiling OpenRouter
# applies the model default, and a truncated response costs a full call for
# nothing. Call B emits less than call A, but not by enough to risk it.
MAX_OUTPUT_TOKENS = 12000

_METHODOLOGY_PROMPT_PATH = _PROJECT_ROOT / "config" / "methodology_prompt.md"
_RUBRIC_PATH = _PROJECT_ROOT / "config" / "sales_bible_rubric.yaml"

# Required dimension ids — used to validate the response before it reaches
# the scorer, so a truncated generation fails loudly here rather than
# silently producing a high score from missing dimensions.
_REQUIRED_DIMENSIONS = {
    "customer_profiling", "need_identification", "vision_setting",
    "program_mapping", "fee_and_urgency", "objection_handling", "trust_journey",
}


def _load_system_prompt() -> str:
    if not _METHODOLOGY_PROMPT_PATH.exists():
        raise FileNotFoundError(f"Methodology prompt not found: {_METHODOLOGY_PROMPT_PATH}")
    return _METHODOLOGY_PROMPT_PATH.read_text(encoding="utf-8")


def _slim_rubric(raw_yaml: str) -> str:
    """Send only the machine-checkable parts of the rubric.

    sales_bible_rubric.yaml is written to be read by people as well as models —
    provenance headers, rationale comments, version notes. None of that helps
    the model judge a call, and it is ~1.2k input tokens on every single call.
    Strip it here rather than making the source file less readable.
    """
    import yaml as _yaml
    try:
        d = _yaml.safe_load(raw_yaml)
        keep = ("id", "name", "chapter", "weight", "applicability", "what_to_look_for",
                "anchors", "penalty_signals", "stages", "rules", "band_mapping",
                "scoring_mode")
        slim = {
            "bands": d["bands"],
            "evidence_policy": d["evidence_policy"],
            "dimensions": [{k: v for k, v in dim.items() if k in keep}
                           for dim in d["dimensions"]],
            "diagnostics": d.get("diagnostics", {}),
        }
        return _yaml.safe_dump(slim, sort_keys=False, allow_unicode=True, width=100)
    except Exception:
        return raw_yaml   # never let a formatting nicety break the call


def _build_user_message(
    cleaned_vtt_path: str,
    metrics: dict,
    sales_pitch_path: str | None = None,
) -> str:
    transcript = Path(cleaned_vtt_path).read_text(encoding="utf-8", errors="replace")
    rubric = _slim_rubric(_RUBRIC_PATH.read_text(encoding="utf-8"))

    # Strip the example blocks from metrics before sending — they duplicate
    # transcript content the model already has and inflate input tokens.
    slim = {k: v for k, v in metrics.items()
            if not k.endswith("_examples")}

    msg = (
        "## Cleaned Transcript\n\n"
        f"{transcript}\n\n"
        "## Rubric\n\n"
        f"{rubric}\n\n"
        "## Conversation Metrics\n\n"
        "These were computed programmatically from the transcript. They are "
        "ground truth. Where they conflict with your impression, they win.\n\n"
        "```json\n"
        f"{json.dumps(slim, indent=2)}\n"
        "```\n\n"
    )

    if sales_pitch_path and Path(sales_pitch_path).exists():
        msg += "## Sales Pitch\n\n" + Path(sales_pitch_path).read_text(
            encoding="utf-8", errors="replace") + "\n\n"

    msg += (
        "Assess the call against the rubric. Assign a band per dimension with "
        "verbatim evidence. Return only the JSON object. Do not compute scores."
    )
    return msg


def _call_openrouter(system_prompt: str, user_message: str, model: str) -> tuple[str, dict]:
    """Call OpenRouter and return the raw text response and token usage."""
    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to your .env file.")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://accredian.com",
            "X-Title": "Accredian Call Quality Agent",
        },
    )

    def _create(use_json_mode: bool):
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kwargs)

    response = _create(use_json_mode=True)
    content, diag = _extract(response)

    if not content:
        # Not all OpenRouter providers support response_format=json_object.
        # Those that don't may return HTTP 200 with empty content rather than
        # an error. The prompt already demands raw JSON, so retry without the
        # flag before giving up — this is a different failure from truncation
        # and a corrective prompt does nothing for it.
        print(f"[methodology] empty response with json_mode on ({diag}); "
              f"retrying without response_format", flush=True)
        response = _create(use_json_mode=False)
        content, diag2 = _extract(response)
        if not content:
            raise RuntimeError(
                "Model returned EMPTY content twice, with and without "
                f"response_format.\n  attempt 1: {diag}\n  attempt 2: {diag2}\n"
                "This is not a JSON formatting problem — nothing came back. "
                "Check the model supports this context size, and look at the "
                "*.debug.json dump next to the raw response file."
            )

    usage = response.usage
    return content, {
        "finish_reason": getattr(response.choices[0], "finish_reason", None),
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        "total_tokens": getattr(usage, "total_tokens", 0) if usage else 0,
    }


def _extract(response) -> tuple[str, str]:
    """Pull content out of an OpenRouter response, or explain why there is none.

    OpenRouter surfaces provider errors in the response BODY with HTTP 200, so
    the SDK does not raise. Reading `.choices[0].message.content or ""` turns
    every one of those into an indistinguishable empty string.
    """
    try:
        dump = response.model_dump()
    except Exception:
        dump = {}

    err = dump.get("error")
    if err:
        return "", f"provider error: {err}"

    choices = dump.get("choices") or []
    if not choices:
        return "", f"no choices returned; body={str(dump)[:400]}"

    ch = choices[0]
    content = (ch.get("message") or {}).get("content")
    if content and content.strip():
        return content, "ok"

    return "", (
        f"empty content; finish_reason={ch.get('finish_reason')}, "
        f"native_finish_reason={ch.get('native_finish_reason')}, "
        f"model={dump.get('model')}, provider={dump.get('provider')}, "
        f"usage={dump.get('usage')}"
    )


def _parse_json_response(raw: str) -> dict:
    """Parse the LLM response, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()
    return json.loads(text)


def _validate(result: dict) -> None:
    """Fail loudly on a structurally incomplete response.

    A truncated generation that drops three dimensions would otherwise be
    scored as 'those stages did not occur' and inflate the methodology score.
    """
    dims = result.get("dimensions")
    if not isinstance(dims, list):
        raise ValueError("Methodology response missing 'dimensions' array")

    got = {d.get("id") for d in dims if isinstance(d, dict)}
    missing = _REQUIRED_DIMENSIONS - got
    if missing:
        raise ValueError(f"Methodology response missing dimensions: {sorted(missing)}")

    valid_bands = {"not_applicable", "missing", "average", "good", "great", None}
    for d in dims:
        if d.get("band") not in valid_bands:
            raise ValueError(f"Invalid band '{d.get('band')}' for dimension '{d.get('id')}'")


def run_methodology(
    pipeline_id: str,
    cleaned_vtt_path: str,
    model: str,
    metrics: dict,
    sales_pitch_path: str | None = None,
) -> dict[str, Any]:
    """
    Run Sales Bible methodology assessment on a cleaned transcript.

    Args:
        metrics: output of src.metrics.conversational.compute_metrics(),
                 produced by clean_service. Passed to the model as ground truth.

    Returns:
        {
          "methodology_json_path": str,
          "methodology": dict,
          "model_used": str,
          "tokens_utilized": int,
        }

    Raises:
        RuntimeError if the LLM fails to return valid JSON after two attempts.
    """
    system_prompt = _load_system_prompt()
    user_message = _build_user_message(cleaned_vtt_path, metrics, sales_pitch_path)

    raw, usage = _call_openrouter(system_prompt, user_message, model)

    try:
        result = _parse_json_response(raw)
        _validate(result)
    except (json.JSONDecodeError, ValueError) as first_error:
        if usage.get("finish_reason") == "length":
            # Truncation, not a format misunderstanding. Re-prompting adds
            # input tokens and leaves the ceiling where it was.
            raise RuntimeError(
                f"Methodology response was TRUNCATED at the output limit "
                f"({usage.get('completion_tokens')} tokens, max_tokens="
                f"{MAX_OUTPUT_TOKENS}). Raise MAX_OUTPUT_TOKENS or reduce "
                f"missed_opportunities to 1 per dimension."
            ) from first_error
        correction = (
            f"Your previous response was rejected: {first_error}. "
            "Return only the raw JSON object with all seven dimension ids present "
            "— no markdown, no fences, no explanation."
        )
        raw, usage2 = _call_openrouter(system_prompt, user_message + "\n\n" + correction, model)
        usage = {k: usage.get(k, 0) + usage2.get(k, 0) for k in usage2}
        try:
            result = _parse_json_response(raw)
            _validate(result)
        except (json.JSONDecodeError, ValueError) as exc:
            stem = Path(cleaned_vtt_path).stem.replace(".cleaned", "")
            output_dir = _PROJECT_ROOT / "data" / "output" / pipeline_id / "report"
            output_dir.mkdir(parents=True, exist_ok=True)
            raw_path = output_dir / f"{stem}.raw_methodology_response.txt"
            raw_path.write_text(raw or "<empty response>", encoding="utf-8")
            # An empty raw file tells you nothing. Dump what we know beside it.
            (output_dir / f"{stem}.methodology.debug.json").write_text(
                json.dumps({
                    "error": str(exc),
                    "raw_length": len(raw or ""),
                    "usage": usage,
                    "model": model,
                    "prompt_chars": len(user_message),
                    "approx_input_tokens": len(user_message) // 4,
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                }, indent=2), encoding="utf-8")
            raise RuntimeError(
                f"Methodology assessment returned invalid output after two attempts: {exc}. "
                f"Raw response saved to {raw_path}"
            ) from exc

    stem = Path(cleaned_vtt_path).stem.replace(".cleaned", "")
    output_dir = _PROJECT_ROOT / "data" / "output" / pipeline_id / "report"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{stem}.methodology.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "methodology_json_path": str(out_path),
        "methodology": result,
        "model_used": model,
        "tokens_utilized": usage.get("total_tokens", 0),
    }