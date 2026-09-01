"""
Deterministic conversational metrics (Layer 0).

Everything countable is counted here, in Python, and then handed to the
methodology LLM as *facts*. The model interprets; it never estimates.

Rationale: LLMs are unreliable at counting occurrences across a long
transcript, and asking them to do so is the single largest source of
run-to-run score drift. Talk ratio, monologue length, callback phrases and
filler counts are all exactly computable — so compute them.

Usage
-----
    from src.metrics.conversational import compute_metrics, Turn

    turns = [Turn("SALES_REP", 0.0, 8.4, "Hi Rani, thanks for taking my call..."), ...]
    metrics = compute_metrics(turns, customer_name="Rani")
    # -> dict, JSON-serialisable, injected into the methodology prompt
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence


# =============================================================================
# Lexicon
# =============================================================================
# NOTE ON LANGUAGE: these patterns assume English / Hinglish code-switching.
# Romanized Hindi equivalents are included where a direct mapping exists.
# If your calls are substantially Hindi, extend these lists — every phrase list
# here is additive and safe to grow. Do NOT translate by machine; the phrasings
# below are lifted from the Bible's own wording.

PERSONALIZATION_CALLBACKS = [
    r"\bas you (mentioned|said|shared|told me)\b",
    r"\bbased on what you (shared|said|mentioned|told)\b",
    r"\byou (mentioned|told me|said) (earlier|that|about)\b",
    r"\bwhen you spoke about\b",
    r"\bconsidering your (experience|role|background|profile)\b",
    r"\bgiven your (current role|experience|background|profile)\b",
    r"\bkeeping your (long[- ]term )?(goal|aspiration|experience)\b",
    r"\bsince (you mentioned|your (goal|aspiration) is)\b",
    r"\bone thing that stood out\b",
    r"\bthis (directly )?addresses the (challenge|gap|concern) (you|we)\b",
    r"\bthe gap we discussed\b",
    r"\bjaisa (aapne|apne) (bataya|kaha)\b",          # Hinglish
]

ALIGNMENT_CHECKINS = [
    r"\bdoes this (connect|align|resonate|fit)\b",
    r"\bdoes this address\b",
    r"\bcan you (relate|see how)\b",
    r"\bhow does this compare\b",
    r"\bis this the kind of\b",
    r"\bwhich of these (areas|resonates)\b",
    r"\bdoes that answer your\b",
    r"\bwould you agree\b",
    r"\bis that how you were looking at it\b",
    r"\bdoes this direction make sense\b",
]

# Ch 5 explicitly names these as scripted-sounding when repeated.
REPETITIVE_ACKS = [r"\bgreat\b", r"\bawesome\b", r"\bperfect\b", r"\bwonderful\b", r"\bexcellent\b"]

# The Bible's preferred alternatives.
GENUINE_ACKS = [
    r"\bthat'?s interesting\b",
    r"\bi would like to understand that better\b",
    r"\bthat sounds like an important\b",
    r"\bthat must have been\b",
    r"\bi can understand why\b",
    r"\bthat'?s a (significant|meaningful) \b",
]

EMPATHY_MARKERS = [
    r"\bi'?m sorry to hear\b",
    r"\bi am sorry to hear\b",
    r"\bi can imagine (that|how)\b",
    r"\bthat must have been (challenging|difficult|hard)\b",
    r"\bi understand[,.]? it can be\b",
    r"\bbalancing multiple priorities\b",
    r"\bit can be frustrating\b",
]

# Ch 9: "Urgency creates momentum. Pressure creates resistance."
PRESSURE_PHRASES = [
    r"\byou'?ll lose (the|this) opportunity\b",
    r"\blast chance\b",
    r"\byou have to decide (now|today)\b",
    r"\bdecide right now\b",
    r"\bonly (one|two|1|2) seats? (left|remaining)\b",
    r"\bi (spoke|talked) to my manager\b",
    r"\bthis (offer|price) (expires|ends) (today|in an hour)\b",
    r"\bif you don'?t (book|pay|confirm) (today|now)\b",
    r"\bnever (get|find) (this|such) (again|an offer)\b",
]

SUMMARY_CONFIRM = [
    r"\blet me summari[sz]e\b",
    r"\bso (just )?to summari[sz]e\b",
    r"\bhave i understood (this|your|you)\b",
    r"\bis my understanding correct\b",
    r"\bso from what i understand\b",
    r"\bdid i (get|capture) that right\b",
    r"\bcorrect me if i'?m wrong\b",
]

FEE_MENTION = [
    r"\b\d[\d,]{4,}\s*(rupees|rs\.?|inr)?\b",
    r"\b\d+(\.\d+)?\s*(lakh|lakhs|lac|l)\b",
    r"\bprogram (fee|investment|cost)\b",
    r"\btotal (fee|investment|amount)\b",
    r"\bemi\b",
    r"\bscholarship\b",
]

DIAGNOSTIC_QUESTIONS = [
    r"\bwhat (specifically )?would you like to (think|think about|discuss)\b",
    r"\bwhat'?s the biggest factor\b",
    r"\bmay i (understand|ask) what\b",
    r"\bis it the (program|investment|overall|monthly)\b",
    r"\bwhat budget (did|had) you\b",
    r"\bis your concern about\b",
    r"\bwhat'?s (still )?holding you back\b",
    r"\bwhat would help you feel\b",
    r"\bcan you help me understand that\b",
    r"\bcould you elaborate\b",
]

OBJECTION_CUES = [
    r"\bneed (some )?time\b",
    r"\bthink about it\b",
    r"\btoo expensive\b",
    r"\bout of (my )?budget\b",
    r"\boutside (my )?budget\b",
    r"\bdiscuss with my (family|wife|husband|spouse)\b",
    r"\bcompar(e|ing) (a few |other )?programs?\b",
    r"\bjust started my research\b",
    r"\bnot ready\b",
    r"\bget back to you\b",
    r"\bcall me (later|back)\b",
    r"\bsoch ke bat", # Hinglish: "soch ke batata hoon"
]

OPEN_Q_STARTERS = r"^(what|how|why|tell me|help me understand|walk me|describe|in what|which|when you)"
CLOSED_Q_STARTERS = r"^(is|are|do|does|did|can|could|would|will|have|has|shall|should|was|were|any)"

# Reps rarely open a question with the interrogative word. "So how many years..."
# and "And what was your last designation?" must classify as open questions, so
# strip leading discourse markers before matching.
DISCOURSE_LEAD = re.compile(
    r"^\W*(?:(?:so|and|ok|okay|alright|right|great|perfect|awesome|wonderful|now|"
    r"just|then|also|actually|basically|but|well|sir|ma'?am|acha|haan)\b[\s,.]*)+",
    re.IGNORECASE,
)

# Words too common to signal topical carry-over between turns.
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "to", "of", "in", "on",
    "for", "with", "at", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "i", "you", "he", "she", "it", "we", "they", "me", "my", "your", "our", "their",
    "this", "that", "these", "those", "have", "has", "had", "do", "does", "did", "will",
    "would", "can", "could", "should", "am", "not", "no", "yes", "ok", "okay", "just",
    "very", "really", "actually", "basically", "like", "know", "think", "want", "get",
}


# =============================================================================
# Data model
# =============================================================================

@dataclass
class Turn:
    """One diarized utterance."""
    speaker: str          # "SALES_REP" | "CUSTOMER"
    start: float          # seconds
    end: float            # seconds
    text: str

    @property
    def is_rep(self) -> bool:
        return self.speaker.upper().startswith("SALES")

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def words(self) -> list[str]:
        return re.findall(r"[a-zA-Z']+", self.text)


@dataclass
class _Hit:
    pattern: str
    timestamp: str
    quote: str


# =============================================================================
# Helpers
# =============================================================================

def _mmss(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _find(patterns: Sequence[str], turns: Iterable[Turn]) -> list[_Hit]:
    """Return every (pattern, timestamp, quote) match across the given turns."""
    hits: list[_Hit] = []
    for t in turns:
        low = t.text.lower()
        for p in patterns:
            for m in re.finditer(p, low, flags=re.IGNORECASE):
                snippet = t.text[max(0, m.start() - 40): m.end() + 60].strip()
                hits.append(_Hit(p, _mmss(t.start), snippet))
    return hits


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _strip_lead(text: str) -> str:
    """Remove leading discourse markers so 'So how many years...' matches the
    open-question pattern rather than falling through unclassified."""
    return DISCOURSE_LEAD.sub("", text.lower().strip())


def _questions(turn: Turn) -> list[str]:
    """Question-like sentences. Catches both '?' and interrogative openers,
    since STT punctuation is unreliable."""
    out = []
    for s in _sentences(turn.text):
        core = _strip_lead(s)
        if s.endswith("?") or re.match(OPEN_Q_STARTERS, core) or re.match(CLOSED_Q_STARTERS, core):
            out.append(s)
    return out


def _classify_question(q: str) -> str:
    core = _strip_lead(q)
    if re.match(OPEN_Q_STARTERS, core):
        return "open"
    if re.match(CLOSED_Q_STARTERS, core):
        return "closed"
    return "other"


def _content_words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", text)} - STOPWORDS


# =============================================================================
# Main entry point
# =============================================================================

def compute_metrics(turns: Sequence[Turn], customer_name: str | None = None) -> dict:
    """Compute all deterministic conversational metrics for one call.

    Returns a flat, JSON-serialisable dict. Every count that carries evidence
    also returns up to 3 example quotes with timestamps, so the LLM can cite
    them and the HTML report can display them.
    """
    rep_turns = [t for t in turns if t.is_rep]
    cust_turns = [t for t in turns if not t.is_rep]

    rep_words = sum(len(t.words) for t in rep_turns)
    cust_words = sum(len(t.words) for t in cust_turns)
    total_words = rep_words + cust_words
    call_seconds = max((t.end for t in turns), default=0.0)

    m: dict = {
        "call_duration_sec": round(call_seconds, 1),
        "total_words": total_words,
        "rep_words": rep_words,
        "customer_words": cust_words,
        "rep_talk_ratio_pct": round(100 * rep_words / total_words, 1) if total_words else 0.0,
        "rep_turns": len(rep_turns),
        "customer_turns": len(cust_turns),
        "avg_customer_words_per_turn": round(cust_words / len(cust_turns), 1) if cust_turns else 0.0,
    }

    # -- Monologue analysis (Ch 7 & 8: "Speaking continuously for 5-10 minutes")
    m.update(_monologues(turns))

    # -- Questioning behaviour (Ch 5 & 6)
    m.update(_question_metrics(turns, rep_turns))

    # -- Phrase-based behaviours
    m.update(_phrase_metrics(rep_turns))

    # -- Acknowledgement quality (Ch 5 "Mistakes to Avoid")
    m.update(_acknowledgement_metrics(turns))

    # -- Customer name usage (Ch 7 "Not using customer name")
    m["customer_name_count"] = (
        len(re.findall(rf"\b{re.escape(customer_name.split()[0])}\b",
                       " ".join(t.text for t in rep_turns), re.IGNORECASE))
        if customer_name else None
    )

    # -- Rule of Three (Ch 9): did the rep stop talking after stating the fee?
    m.update(_rule_of_three(turns))

    # -- Objection handling proxies (Ch 10)
    m.update(_objection_metrics(turns))

    # -- Engagement trend: is the customer opening up or shutting down?
    m.update(_engagement_trend(turns, cust_turns))

    return m


# =============================================================================
# Metric groups
# =============================================================================

def _monologues(turns: Sequence[Turn]) -> dict:
    """A monologue is a contiguous run of rep turns with no customer content
    in between. Customer backchannels ('yes', 'okay', 'hmm') do NOT break it —
    the Bible's concern is passive listening, and a grunt is passive."""
    BACKCHANNEL = re.compile(r"^\W*(yes|yeah|yep|ok|okay|hmm+|mhm+|right|sure|ji|haan|acha)\W*$", re.I)

    blocks: list[tuple[float, float, int]] = []  # (start, end, words)
    cur_start = cur_end = None
    cur_words = 0

    for t in turns:
        if t.is_rep:
            if cur_start is None:
                cur_start = t.start
            cur_end = t.end
            cur_words += len(t.words)
        elif BACKCHANNEL.match(t.text.strip()) or len(t.words) <= 2:
            if cur_start is not None:
                cur_end = max(cur_end or t.end, t.end)
        else:
            if cur_start is not None:
                blocks.append((cur_start, cur_end, cur_words))
            cur_start = cur_end = None
            cur_words = 0
    if cur_start is not None:
        blocks.append((cur_start, cur_end, cur_words))

    if not blocks:
        return {
            "longest_rep_monologue_sec": 0.0,
            "longest_rep_monologue_at": None,
            "longest_rep_monologue_words": 0,
            "monologues_over_90s": 0,
            "monologues_over_180s": 0,
        }

    longest = max(blocks, key=lambda b: b[1] - b[0])
    return {
        "longest_rep_monologue_sec": round(longest[1] - longest[0], 1),
        "longest_rep_monologue_at": _mmss(longest[0]),
        "longest_rep_monologue_words": longest[2],
        "monologues_over_90s": sum(1 for b in blocks if b[1] - b[0] > 90),
        "monologues_over_180s": sum(1 for b in blocks if b[1] - b[0] > 180),
    }


def _question_metrics(turns: Sequence[Turn], rep_turns: Sequence[Turn]) -> dict:
    """Counts, open/closed split, and second-level question detection.

    'Second-level' (Ch 5): a rep question that reuses content words from the
    customer's immediately preceding answer. Heuristic, but a reliable proxy —
    it distinguishes 'What made you move into operations?' (reuses 'operations')
    from the next scripted item on the list.
    """
    open_q = closed_q = 0
    all_q: list[_Hit] = []
    for t in rep_turns:
        for q in _questions(t):
            all_q.append(_Hit("question", _mmss(t.start), q))
            kind = _classify_question(q)
            if kind == "open":
                open_q += 1
            elif kind == "closed":
                closed_q += 1

    second_level: list[_Hit] = []
    for i, t in enumerate(turns):
        if not t.is_rep or i == 0:
            continue
        prev = turns[i - 1]
        if prev.is_rep or len(prev.words) < 5:
            continue
        prev_content = _content_words(prev.text)
        for q in _questions(t):
            if _content_words(q) & prev_content:
                second_level.append(_Hit("second_level", _mmss(t.start), q))

    minutes = max(1e-6, max((t.end for t in turns), default=0.0) / 60)
    return {
        "rep_question_count": len(all_q),
        "rep_questions_per_min": round(len(all_q) / minutes, 2),
        "open_question_count": open_q,
        "closed_question_count": closed_q,
        "open_question_ratio": round(open_q / (open_q + closed_q), 2) if (open_q + closed_q) else 0.0,
        "second_level_question_count": len(second_level),
        "second_level_question_examples": [
            {"timestamp": h.timestamp, "quote": h.quote} for h in second_level[:3]
        ],
    }


def _phrase_metrics(rep_turns: Sequence[Turn]) -> dict:
    def pack(name: str, patterns: Sequence[str]) -> dict:
        hits = _find(patterns, rep_turns)
        return {
            f"{name}_count": len(hits),
            f"{name}_examples": [{"timestamp": h.timestamp, "quote": h.quote} for h in hits[:3]],
        }

    out: dict = {}
    out.update(pack("personalization_callback", PERSONALIZATION_CALLBACKS))
    out.update(pack("alignment_checkin", ALIGNMENT_CHECKINS))
    out.update(pack("empathy_marker", EMPATHY_MARKERS))
    out.update(pack("pressure_phrase", PRESSURE_PHRASES))
    out.update(pack("summary_confirm", SUMMARY_CONFIRM))
    out.update(pack("diagnostic_question", DIAGNOSTIC_QUESTIONS))
    return out


def _acknowledgement_metrics(turns: Sequence[Turn]) -> dict:
    """Ch 5: repetitive scripted acknowledgement, and the 'Okay → next question'
    pattern that 'creates emotional distance'."""
    rep_turns = [t for t in turns if t.is_rep]
    rep_replies = 0
    repetitive = 0
    genuine = 0
    okay_advance = 0
    examples: list[dict] = []

    for i, t in enumerate(turns):
        if not t.is_rep or i == 0 or turns[i - 1].is_rep:
            continue
        if len(turns[i - 1].words) < 4:      # not a real answer
            continue
        rep_replies += 1
        opening = " ".join(t.text.split()[:6]).lower()

        if any(re.search(p, opening, re.I) for p in REPETITIVE_ACKS):
            repetitive += 1
            if len(examples) < 3:
                examples.append({"timestamp": _mmss(t.start), "quote": t.text[:110]})
        if any(re.search(p, t.text.lower(), re.I) for p in GENUINE_ACKS):
            genuine += 1
        # "Okay." followed straight by a question, with no acknowledgement.
        if re.match(r"^\W*(ok|okay|noted|alright)\b", opening, re.I) and _questions(t):
            okay_advance += 1

    return {
        "rep_replies_to_substantive_answers": rep_replies,
        "repetitive_ack_count": repetitive,
        "repetitive_ack_ratio": round(repetitive / rep_replies, 2) if rep_replies else 0.0,
        "repetitive_ack_examples": examples,
        "genuine_ack_count": genuine,
        "okay_advance_count": okay_advance,
    }


def _rule_of_three(turns: Sequence[Turn], window_sec: float = 15.0) -> dict:
    """Ch 9: 'State the fee. State the flexibility. Ask a question. Then stop
    talking.'

    The measurement must start at the *fee mention*, not at the end of the turn
    containing it. Reps almost always over-explain within the same breath, so
    anchoring to turn end would score the worst offenders as compliant. We
    locate the mention inside the turn and interpolate its timestamp from word
    position, then count every rep word from there to the window edge.
    """
    fee_turn = fee_pos = None
    for t in turns:
        if not t.is_rep:
            continue
        matches = [m.start() for p in FEE_MENTION
                   for m in re.finditer(p, t.text, re.I)]
        if matches:
            fee_turn, fee_pos = t, min(matches)
            break

    if fee_turn is None:
        return {
            "fee_discussed": False,
            "fee_first_mention_at": None,
            "rep_words_after_fee_15s": None,
            "words_after_fee_same_turn": None,
            "question_asked_at_fee": None,
            "customer_spoke_after_fee": None,
        }

    # Interpolate the mention's timestamp from its position in the turn.
    total_chars = max(1, len(fee_turn.text))
    offset = fee_turn.duration * (fee_pos / total_chars)
    mention_time = fee_turn.start + offset
    cutoff = mention_time + window_sec

    tail = fee_turn.text[fee_pos:]
    tail_words = re.findall(r"[a-zA-Z']+", tail)
    # Words in the remainder of this turn that fall inside the window.
    remaining_dur = max(1e-6, fee_turn.end - mention_time)
    frac_in_window = min(1.0, window_sec / remaining_dur)
    same_turn_words = int(round(len(tail_words) * frac_in_window))

    later_words = sum(
        len(t.words) for t in turns
        if t.is_rep and t is not fee_turn and mention_time <= t.start < cutoff
    )
    cust_after = any(
        not t.is_rep and mention_time <= t.start < cutoff and len(t.words) > 2
        for t in turns
    )

    return {
        "fee_discussed": True,
        "fee_first_mention_at": _mmss(mention_time),
        "rep_words_after_fee_15s": same_turn_words + later_words,
        "words_after_fee_same_turn": len(tail_words),
        "question_asked_at_fee": bool(_questions(fee_turn)),
        "customer_spoke_after_fee": cust_after,
    }


def _objection_metrics(turns: Sequence[Turn]) -> dict:
    """Ch 10: for each customer objection, did the rep ask a diagnostic
    question before responding at length?"""
    events: list[dict] = []
    for i, t in enumerate(turns):
        if t.is_rep or not any(re.search(p, t.text, re.I) for p in OBJECTION_CUES):
            continue
        nxt = next((u for u in turns[i + 1:] if u.is_rep), None)
        if nxt is None:
            events.append({
                "timestamp": _mmss(t.start),
                "objection": t.text[:140],
                "rep_response": None,
                "diagnostic_question_asked": False,
                "rep_response_words": 0,
            })
            continue
        diagnostic = any(re.search(p, nxt.text, re.I) for p in DIAGNOSTIC_QUESTIONS)
        events.append({
            "timestamp": _mmss(t.start),
            "objection": t.text[:140],
            "rep_response": nxt.text[:180],
            "diagnostic_question_asked": diagnostic or bool(_questions(nxt)),
            "rep_response_words": len(nxt.words),
        })

    return {
        "objection_count": len(events),
        "objections_with_diagnostic_response": sum(1 for e in events if e["diagnostic_question_asked"]),
        "objection_events": events[:6],
    }


def _engagement_trend(turns: Sequence[Turn], cust_turns: Sequence[Turn]) -> dict:
    """Is the customer opening up or closing down? Compare average customer
    words per turn in the first vs second half of the call."""
    if len(cust_turns) < 4:
        return {"customer_engagement_trend": "insufficient_data",
                "customer_words_first_half": None,
                "customer_words_second_half": None}

    mid = max((t.end for t in turns), default=0.0) / 2
    first = [t for t in cust_turns if t.start < mid]
    second = [t for t in cust_turns if t.start >= mid]
    if not first or not second:
        return {"customer_engagement_trend": "insufficient_data",
                "customer_words_first_half": None,
                "customer_words_second_half": None}

    a = sum(len(t.words) for t in first) / len(first)
    b = sum(len(t.words) for t in second) / len(second)
    if b > a * 1.25:
        trend = "opening_up"
    elif b < a * 0.75:
        trend = "shutting_down"
    else:
        trend = "steady"
    return {
        "customer_engagement_trend": trend,
        "customer_words_first_half": round(a, 1),
        "customer_words_second_half": round(b, 1),
    }


# =============================================================================
# Transcript adapters
# =============================================================================

_VTT_TS = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
# The pipeline writes "[Rani]: text" — a real name, not a role. Capture whatever
# is inside the brackets and resolve it against a role map supplied by the caller.
_SPEAKER = re.compile(r"^\s*\[([^\]]{1,60})\]\s*:\s*")
_SPEAKER_BARE = re.compile(r"^\s*(SALES_REP|CUSTOMER|REP|AGENT)\s*[:\-]\s*", re.I)


def parse_utterances(utterances: Sequence[dict]) -> list[Turn]:
    """Adapter for the pipeline's in-memory utterance dicts.

    This is the PREFERRED entry point. `clean_service.run_clean()` already holds
    utterances carrying an authoritative `role` field assigned by
    `label_speakers()`, so consuming them directly avoids re-parsing the VTT and
    is immune to however `format_cleaned_vtt()` chooses to render speaker labels.

    Expected keys: role ("SALES_REP"/"CUSTOMER"), start_sec, end_sec, text.
    Falls back to start/end and start_time/end_time for other callers.
    """
    turns: list[Turn] = []
    for u in utterances:
        text = (u.get("text") or "").strip()
        if not text:
            continue
        role = (u.get("role") or "").upper()
        if role not in ("SALES_REP", "CUSTOMER"):
            # No role assigned — fall back to the speaker field, defaulting to rep.
            role = "CUSTOMER" if "CUSTOMER" in str(u.get("speaker", "")).upper() else "SALES_REP"
        turns.append(Turn(
            speaker=role,
            start=float(u.get("start_sec", u.get("start", u.get("start_time", 0.0))) or 0.0),
            end=float(u.get("end_sec", u.get("end", u.get("end_time", 0.0))) or 0.0),
            text=text,
        ))
    return _merge_adjacent(turns)


def parse_vtt(content: str, role_map: dict[str, str] | None = None) -> list[Turn]:
    """Parse a cleaned WebVTT transcript into Turns.

    Fallback path for standalone/CLI use. Prefer `parse_utterances()` inside the
    pipeline, where roles are already known.

    `role_map` maps the bracketed speaker label to a role, e.g.
    ``{"Amit": "SALES_REP", "Rani": "CUSTOMER"}``. Without it, bare
    SALES_REP/CUSTOMER labels are still recognised; any other label raises,
    because silently defaulting every turn to SALES_REP would corrupt every
    metric downstream while looking like it worked.
    """
    role_map = {k.strip().lower(): v for k, v in (role_map or {}).items()}
    turns: list[Turn] = []
    unresolved: set[str] = set()

    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        ts_line = next((l for l in lines if _VTT_TS.search(l)), None)
        if not ts_line:
            continue
        g = _VTT_TS.search(ts_line).groups()
        start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        end = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        body = " ".join(lines[lines.index(ts_line) + 1:]).strip()
        if not body:
            continue

        speaker = None
        m = _SPEAKER.match(body)
        if m:
            label = m.group(1).strip()
            body = _SPEAKER.sub("", body)
            upper = label.upper().replace(" ", "_")
            if upper in ("SALES_REP", "REP", "AGENT"):
                speaker = "SALES_REP"
            elif upper == "CUSTOMER":
                speaker = "CUSTOMER"
            elif label.lower() in role_map:
                speaker = role_map[label.lower()]
            else:
                unresolved.add(label)
                speaker = "SALES_REP"
        else:
            m2 = _SPEAKER_BARE.match(body)
            if m2:
                lbl = m2.group(1).upper()
                speaker = "CUSTOMER" if lbl == "CUSTOMER" else "SALES_REP"
                body = _SPEAKER_BARE.sub("", body)
            else:
                speaker = "SALES_REP"

        turns.append(Turn(speaker, start, end, body.strip()))

    if unresolved:
        raise ValueError(
            "Unresolved speaker labels in VTT: "
            + ", ".join(sorted(unresolved))
            + ". Pass role_map={'Name': 'SALES_REP'|'CUSTOMER'}, or use "
              "parse_utterances() with the pipeline's role-tagged utterances."
        )
    return _merge_adjacent(turns)


def parse_json_turns(data: list[dict]) -> list[Turn]:
    """Back-compat alias for parse_utterances()."""
    return parse_utterances(data)


def _merge_adjacent(turns: list[Turn], gap: float = 1.0) -> list[Turn]:
    """STT often fragments one utterance across several cues. Merge same-speaker
    runs so monologue and turn counts reflect conversation, not cue boundaries."""
    if not turns:
        return []
    merged = [turns[0]]
    for t in turns[1:]:
        last = merged[-1]
        if t.speaker == last.speaker and t.start - last.end <= gap:
            merged[-1] = Turn(last.speaker, last.start, t.end, f"{last.text} {t.text}".strip())
        else:
            merged.append(t)
    return merged