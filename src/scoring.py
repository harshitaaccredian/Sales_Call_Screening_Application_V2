"""
Deterministic scoring engine (Layer 3).

The LLM emits *bands* and *evidence*. This module turns them into a number.
Same inputs always produce the same score — that property is the whole point,
and it is why the model is never asked to do arithmetic.

Inputs
------
compliance_result : dict   output of analysis_prompt.md  (incidents, checklist)
methodology_result: dict   output of methodology_prompt.md (dimension bands)
metrics           : dict   output of src.metrics.conversational.compute_metrics

Output
------
A `overall_call_score` object that drops straight into the existing report JSON,
plus a `methodology` block for the new HTML section.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Human-readable text for LLM-judged penalty signals, so the report explains
# the deduction rather than showing a raw identifier.
SIGNAL_LABELS = {
    "fee_before_fit": "Moved to the fee before confirming program fit",
    "artificial_urgency": "Manufactured urgency rather than stating a genuine reason",
    "no_next_step": "Call ended without a defined next step",
    "accepted_deferral": "Accepted 'I need time' without a single diagnostic question",
    "brochure_mode": "Curriculum recited module by module with no link to customer needs",
    "features_not_outcomes": "Described what the program includes, not why it matters",
    "empathy_omission": "Customer disclosed hardship; rep moved straight on",
    "putting_words_in_mouth": "Supplied the customer's skill gap instead of eliciting it",
    "generic_skills_unexplored": "Broad skill named by the customer was never decomposed",
    "solving_confusion_early": "Chose a career direction on the customer's behalf",
    "no_resonance_probe": "Never asked which part resonated — buying signal missed",
    "generic_test_fails": "Explanation would sound identical for any customer",
    "answered_before_understanding": "Responded to an assumed objection without diagnosing",
    "urgency_before_resolution": "Deployed urgency before addressing the concern",
    "multi_objection_dump": "Answered several concerns at once instead of one at a time",
    "argumentative": "Argued the point rather than reducing uncertainty",
    "defensive_tone": "Sounded defensive while discussing price",
}


# =============================================================================
# Config loading
# =============================================================================

def load_config(config_dir: Path | str | None = None) -> tuple[dict, dict]:
    d = Path(config_dir) if config_dir else CONFIG_DIR
    weights = yaml.safe_load((d / "scoring_weights.yaml").read_text(encoding="utf-8"))
    rubric = yaml.safe_load((d / "sales_bible_rubric.yaml").read_text(encoding="utf-8"))
    return weights, rubric


# =============================================================================
# Compliance
# =============================================================================

def score_compliance(incidents: list[dict], cfg: dict) -> dict:
    """Start at max, deduct by severity, compound repeats within a category."""
    c = cfg["compliance"]
    # The compliance budget is components.compliance — a single source of truth.
    # `compliance.start` is accepted only as a legacy override and must agree,
    # otherwise editing the split silently leaves compliance scoring on the old
    # scale and the total can no longer reach 100.
    budget = float(cfg["components"]["compliance"])
    legacy = c.get("start")
    if legacy is not None and float(legacy) != budget:
        raise ValueError(
            f"Config conflict: components.compliance={budget} but "
            f"compliance.start={legacy}. These are the same quantity — set "
            f"components.compliance and delete compliance.start."
        )
    score = budget
    seen: Counter[str] = Counter()
    detail: list[dict] = []

    # Deduct most severe first so the compounding multiplier lands on the
    # repeats rather than arbitrarily on whichever came first in the list.
    order = {"L3": 0, "L2": 1, "L1": 2}
    for inc in sorted(incidents, key=lambda i: order.get(i.get("severity", "L1"), 3)):
        sev = inc.get("severity", "L1")
        base = float(c["deductions"].get(sev, 0))
        category = (inc.get("category") or "Uncategorised").split("—")[0].strip()
        seen[category] += 1
        mult = float(c["repeat_category_multiplier"]) if seen[category] > 1 else 1.0
        applied = base * mult
        score -= applied
        detail.append({
            "id": inc.get("id"),
            "severity": sev,
            "category": category,
            "points": round(applied, 1),
            "repeat": seen[category] > 1,
        })

    score = max(float(c["floor"]), score)
    severities = {i.get("severity") for i in incidents}
    cap = 100
    for sev in ("L3", "L2", "L1"):
        if sev in severities:
            cap = min(cap, int(c["caps"].get(sev, 100)))
            break   # only the highest severity's cap applies

    return {
        "score": round(score, 1),
        "max": budget,
        "cap_applied": cap,
        "highest_severity": next((s for s in ("L3", "L2", "L1") if s in severities), "None"),
        "deduction_detail": detail,
    }


# =============================================================================
# Methodology
# =============================================================================

def score_methodology(methodology_result: dict, metrics: dict, cfg: dict, rubric: dict) -> dict:
    """Weighted band rollup with not-applicable renormalisation, evidence
    enforcement, and penalty signals."""
    mcfg = cfg["methodology"]
    band_values = mcfg["band_values"]
    ev_policy = rubric["evidence_policy"]
    weights = {d["id"]: float(d["weight"]) for d in rubric["dimensions"]}
    names = {d["id"]: d["name"] for d in rubric["dimensions"]}

    dims_in = {d["id"]: d for d in methodology_result.get("dimensions", [])}

    applicable: dict[str, dict] = {}
    not_applicable: list[str] = []
    unevidenced: list[str] = []

    for dim_id, weight in weights.items():
        d = dims_in.get(dim_id)
        if d is None or d.get("band") in (None, "not_applicable"):
            not_applicable.append(dim_id)
            continue

        band = d.get("band", "missing")
        quotes = d.get("evidence", []) or []

        # Evidence enforcement: an unevidenced band above `missing` is demoted.
        if ev_policy.get("demote_if_unevidenced") and band != "missing" and len(quotes) < ev_policy["min_quotes"]:
            band = _demote(band)
            unevidenced.append(dim_id)

        applicable[dim_id] = {
            "id": dim_id,
            "name": names[dim_id],
            "band": band,
            "raw_band": d.get("band"),
            "weight": weight,
            "evidence": quotes[: ev_policy["max_quotes"]],
            "reasoning": d.get("reasoning", ""),
            "missed_opportunities": d.get("missed_opportunities", []),
        }

    total_weight = sum(v["weight"] for v in applicable.values())
    all_weight = sum(weights.values())
    applicable_fraction = total_weight / all_weight if all_weight else 0.0

    # renormalize=True : the score is out of what the call ATTEMPTED. An N/A
    #   criterion's weight is spread over the rest, so a call where the customer
    #   never objected can still reach 60.
    # renormalize=False: the score is out of the FULL rubric. An N/A criterion's
    #   points are simply unavailable, so that same call tops out below 60.
    # This is a policy choice, not a maths one — see the note in the YAML.
    renormalize = bool(mcfg.get("renormalize_on_not_applicable", True))
    base_weight = total_weight if renormalize else all_weight

    max_points = float(cfg["components"]["methodology"])
    earned = 0.0
    for v in applicable.values():
        share = (v["weight"] / base_weight) if base_weight else 0.0
        dim_max = share * max_points
        dim_pts = dim_max * float(band_values.get(v["band"], 0.0))
        # Store UNROUNDED. Rounding here and formatting to 1dp in the renderer
        # double-rounds: 7.8 x 0.34 = 2.652 -> round(_,2) = 2.65 -> "2.6",
        # when the correct 1dp value is 2.7. Format once, at display time.
        v["points"] = dim_pts
        v["points_max"] = dim_max
        # Achievement is band-driven, so this is exactly the band value:
        # 0 / 34 / 70 / 100. There are only four possible values per dimension.
        v["pct"] = round(100 * float(band_values.get(v["band"], 0.0)))
        # Every criterion also reported on a common 0-10 scale. A shared
        # denominator is what makes the scorecard scannable: a manager can
        # compare rows without first reading each row's max.
        v["out_of_ten"] = round(10 * float(band_values.get(v["band"], 0.0)), 1)
        # Effective weight AFTER renormalisation. When a stage is N/A the
        # remaining criteria each carry more, so the raw rubric weight no
        # longer explains the points and a reader checking the arithmetic
        # finds it wrong.
        v["effective_weight"] = round(100 * share, 1)
        v["renormalized"] = abs(share * 100 - v["weight"]) > 0.05
        earned += dim_pts

    # Penalties are a CEILING mechanism, not additive punishment. The band
    # anchors already describe these behaviours, so applying a flat deduction
    # on top double-counts them and floors a weak call to zero regardless of
    # what it did right. Scaling to a share of earned points keeps the signal
    # meaningful on strong calls (where a bad habit should cost real points)
    # without piling on a call the bands have already marked down.
    penalties = _penalties(methodology_result, metrics, cfg)
    penalty_ceiling = float(mcfg.get("penalty_share_of_earned", 0.30)) * earned
    penalties["total_uncapped"] = penalties["total"]
    penalties["total"] = round(min(penalties["total"], penalty_ceiling), 2)
    penalties["proportionally_capped"] = penalties["total"] < penalties["total_uncapped"]
    earned = max(0.0, earned - penalties["total"])

    return {
        "score": round(earned, 1),
        "max": max_points,
        "dimensions": list(applicable.values()),
        "not_applicable": [{"id": i, "name": names[i], "weight": weights[i]}
                           for i in not_applicable],
        "applicable_weight_fraction": round(applicable_fraction, 2),
        "renormalized": renormalize,
        # Ceiling this call could actually reach. Equals max_points when every
        # criterion applies, or when renormalisation is on.
        "achievable": round(max_points * (1.0 if renormalize else applicable_fraction), 1),
        "low_confidence": applicable_fraction < float(mcfg["min_applicable_weight_fraction"]),
        "unevidenced_dimensions": unevidenced,
        "penalties": penalties,
        "trust_journey": methodology_result.get("trust_journey", {}),
        "four_whys": methodology_result.get("four_whys", []),
        "hfte_balance": methodology_result.get("hfte_balance", []),
    }


def _demote(band: str) -> str:
    ladder = ["missing", "average", "good", "great"]
    try:
        return ladder[max(0, ladder.index(band) - 1)]
    except ValueError:
        return "missing"


def _penalties(methodology_result: dict, metrics: dict, cfg: dict) -> dict:
    """Penalty signals, drawn from deterministic metrics wherever possible so
    they cannot drift between runs."""
    pts = cfg["methodology"]["penalty_points"]
    applied: list[dict] = []

    def add(key: str, why: str) -> None:
        if key in pts:
            applied.append({"signal": key, "points": pts[key], "reason": why})

    if metrics.get("repetitive_ack_ratio", 0) >= 0.35:
        add("repetitive_acknowledgement",
            f"Scripted acknowledgement ('Great'/'Perfect') on "
            f"{int(metrics['repetitive_ack_ratio'] * 100)}% of replies")
    if metrics.get("okay_advance_count", 0) >= 3:
        add("okay_and_advance",
            f"'Okay' + immediate next question {metrics['okay_advance_count']} times")
    if metrics.get("monologues_over_180s", 0) >= 1:
        add("monologue_over_180s",
            f"Longest uninterrupted stretch {metrics.get('longest_rep_monologue_sec')}s "
            f"at {metrics.get('longest_rep_monologue_at')}")
    if metrics.get("personalization_callback_count", 0) == 0:
        add("no_personalization_callback",
            "Never referred back to what the customer shared earlier")
    if metrics.get("customer_name_count") == 0:
        add("customer_name_never_used", "Customer's name never used")
    if metrics.get("fee_discussed") and metrics.get("rep_words_after_fee_15s", 0) > 45:
        add("filled_the_silence",
            f"Spoke {metrics['rep_words_after_fee_15s']} words in the 15s after stating the fee "
            f"(Rule of Three: state, ask, stop)")

    # LLM-judged signals that have no deterministic proxy.
    for sig in methodology_result.get("penalty_signals", []):
        if sig in pts and not any(a["signal"] == sig for a in applied):
            applied.append({
                "signal": sig,
                "points": pts[sig],
                "reason": SIGNAL_LABELS.get(sig, sig.replace("_", " ").capitalize()),
            })

    # Double-jeopardy guard.
    suppress = cfg["methodology"].get("suppress_if_compliance_incident", {})
    raised = set(methodology_result.get("_compliance_categories", []))
    kept = []
    for a in applied:
        blockers = suppress.get(a["signal"], [])
        if any(b in raised for b in blockers):
            a["suppressed"] = "Already raised as a compliance incident"
            continue
        kept.append(a)

    total = min(sum(a["points"] for a in kept), float(cfg["methodology"]["max_total_penalty"]))
    return {"total": total, "applied": kept}


# =============================================================================
# Top-level
# =============================================================================

def compute_overall_score(
    compliance_result: dict,
    methodology_result: dict,
    metrics: dict,
    config_dir: Path | str | None = None,
) -> dict:
    """Roll compliance + methodology into the standalone rubric score.

    Deliberately does NOT consume sales-pitch coverage. That feeds the separate,
    pre-existing `overall_call_score` section which renders only when a Sales
    Pitch is uploaded. The two scores are independent measurements of the same
    call and must not be blended.
    """
    cfg, rubric = load_config(config_dir)

    incidents = compliance_result.get("report", {}).get("incidents", compliance_result.get("incidents", []))
    comp = score_compliance(incidents, cfg)

    # Feed compliance categories in so the methodology layer can suppress
    # double-jeopardy penalties.
    methodology_result = dict(methodology_result)
    methodology_result["_compliance_categories"] = [
        (i.get("category") or "").split("—")[0].strip() for i in incidents
    ]

    meth = score_methodology(methodology_result, metrics, cfg, rubric)
    comp_pts, meth_pts = comp["score"], meth["score"]
    total = comp_pts + meth_pts
    cap = comp["cap_applied"]
    capped = total > cap
    total = min(total, cap)
    total = int(round(max(0.0, min(100.0, total))))

    grade = next(g for g in cfg["grades"] if total >= g["min"])

    return {
        "scoring_version": cfg["scoring_version"],
        "rubric_version": rubric["rubric_version"],
        "total_score": total,
        "grade": grade["label"],
        "grade_color": grade["color"],
        "compliance_score": round(comp_pts, 1),
        "compliance_max": float(cfg["components"]["compliance"]),
        "methodology_score": round(meth_pts, 1),
        "methodology_max": float(cfg["components"]["methodology"]),
        "cap_applied": cap if capped else None,
        "cap_reason": (
            f"Capped at {cap} — {comp['highest_severity']} compliance incident present"
            if capped else None
        ),
        "low_confidence": bool(
            meth["low_confidence"]
            or metrics.get("call_duration_sec", 0) < cfg["confidence"]["min_call_seconds"]
            or metrics.get("customer_turns", 0) < cfg["confidence"]["min_customer_turns"]
            or len(meth["unevidenced_dimensions"]) >= cfg["confidence"]["flag_if_unevidenced_dimensions_gte"]
        ),
        "deductions_text": _deductions_text(comp, meth, capped, cap),
        "_compliance": comp,
        "_methodology": meth,
    }


def _deductions_text(comp: dict, meth: dict, capped: bool, cap: int) -> str:
    parts: list[str] = []
    lost_c = comp["max"] - comp["score"]
    if lost_c > 0:
        sev = Counter(d["severity"] for d in comp["deduction_detail"])
        breakdown = ", ".join(f"{n}× {s}" for s, n in sorted(sev.items()))
        parts.append(f"Compliance −{lost_c:.0f} ({breakdown})")

    weak = sorted(
        [d for d in meth["dimensions"] if d["band"] in ("missing", "average")],
        key=lambda d: d["points_max"] - d["points"], reverse=True,
    )[:3]
    if weak:
        parts.append("Methodology −{:.0f} (weakest: {})".format(
            meth["max"] - meth["score"],
            ", ".join(f"{d['name'].split('&')[0].strip()} [{d['band']}]" for d in weak),
        ))
    for p in meth["penalties"]["applied"][:3]:
        parts.append(f"{p['reason']} (−{p['points']})")
    if capped:
        parts.append(f"HARD CAP at {cap} due to {comp['highest_severity']} incident")
    return "Deductions: " + "; ".join(parts) + "." if parts else "No deductions — clean call."