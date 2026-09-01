# """
# Cleans a diarized transcript and outputs one file:
#   - output/<stem>.cleaned.vtt  — WebVTT with normalized speaker labels, term
#                                   corrections, fuzzy matches, and minimal filler
#                                   removal; preserves original timing and structure.

# Accepts three input formats:
#   1. JSON  — our own *.transcript.json produced by transcribe.py
#   2. Plain text — diarization exports from external tools (Otter.ai, Whisper,
#                   Rev.ai, etc.) with speaker labels in common formats
#   3. SRT — SubRip subtitle files with speaker labels in the text lines
#   4. VTT — WebVTT subtitle files with optional inline tags

# Cleaning applied to all formats:
#   - Labels numeric/generic speaker tags as SALES_REP / CUSTOMER / SPEAKER_N
#   - Applies term corrections from config/corrections.json
#   - Applies fuzzy phonetic entity normalization for hard-to-transcribe institute names
#   - Strips only true zero-content fillers (um, uh, hmm) — no semantic words

# Usage:
#     python src/clean.py <transcript_file>   (.json, .txt/.text, .srt, or .vtt)

# Output:
#     output/<stem>.cleaned.vtt
# """

# import os
# import sys
# import json
# import re
# import difflib
# from pathlib import Path


# CORRECTIONS_PATH = Path("config/corrections.json")

# # Heuristic: in Accredian outbound calls, speaker 1 initiates — they're the rep.
# # Speaker 2 is the customer. Override by setting SALES_REP_SPEAKER env var.
# DEFAULT_REP_SPEAKER = 1

# # Entities for Fuzzy Phonetic Matching
# # Add any high-priority, frequently misspelled names here.
# FUZZY_TARGETS = [
#     "Accredian",
#     "E&ICT Academy IIT Kanpur",
#     "IIT Hyderabad",
#     "IIT Guwahati",
#     "IIM Visakhapatnam",
#     "Visakhapatnam",
#     "IIM Lucknow",
#     "SP Jain School of Global Management",
#     "XLRI Delhi",
#     "XLRI",
#     "SP Jain Global"
# ]

# # Plain-text diarization patterns (tried in order, first match wins per line).
# # Each pattern must have a named group 'speaker' and 'text'.
# # Optional named group 'timestamp' is preserved if present.
# DIARIZATION_PATTERNS = [
#     # [00:01:23] Speaker 1: text   or   [01:23] Speaker 1: text
#     re.compile(
#         r"^\[(?P<timestamp>[\d:]+)\]\s*(?P<speaker>[^\:]+?)\s*:\s*(?P<text>.+)$"
#     ),
#     # Speaker 1 (00:01:23): text
#     re.compile(
#         r"^(?P<speaker>[^\(]+?)\s*\((?P<timestamp>[\d:]+)\)\s*:\s*(?P<text>.+)$"
#     ),
#     # Speaker 1: text   (no timestamp)
#     re.compile(
#         r"^(?P<speaker>(?:Speaker|SPEAKER|Rep|Agent|Customer|Caller|Sales)[^\:]*?)\s*:\s*(?P<text>.+)$",
#         re.IGNORECASE,
#     ),
#     # S1: text  or  SP1: text
#     re.compile(
#         r"^(?P<speaker>S[Pp]?\d+)\s*:\s*(?P<text>.+)$"
#     ),
# ]


# def load_corrections() -> dict:
#     if not CORRECTIONS_PATH.exists():
#         print(f"Warning: corrections file not found at {CORRECTIONS_PATH}, skipping.")
#         return {}
#     return json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))


# # ---------------------------------------------------------------------------
# # Loaders
# # ---------------------------------------------------------------------------

# def load_json_transcript(path: Path) -> list[dict]:
#     """Load utterances from our own *.transcript.json format."""
#     data = json.loads(path.read_text(encoding="utf-8"))
#     if "utterances" not in data:
#         raise ValueError(f"Expected 'utterances' key in JSON, not found in {path}")
#     return data["utterances"]


# def _parse_srt_time(s: str) -> float:
#     """Parse one side of an SRT/VTT timestamp (HH:MM:SS,mmm or MM:SS,mmm)."""
#     s = s.strip()
#     m = re.match(r"(\d+):(\d{2}):(\d{2})[,.](\d+)", s)
#     if m:
#         return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
#     m = re.match(r"(\d{1,2}):(\d{2})[,.](\d+)", s)
#     if m:
#         return int(m.group(1)) * 60 + int(m.group(2))
#     return 0.0


# def _sec_to_srt(sec: float) -> str:
#     """Format seconds as HH:MM:SS,000 for SRT output."""
#     sec = int(sec)
#     h = sec // 3600
#     m = (sec % 3600) // 60
#     s = sec % 60
#     return f"{h:02d}:{m:02d}:{s:02d},000"


# def load_srt_transcript(path: Path) -> list[dict]:
#     """
#     Parse an SRT file into utterance dicts.

#     Expected block format:
#         <sequence>
#         HH:MM:SS,mmm --> HH:MM:SS,mmm
#         Speaker: text
#         [continuation lines...]

#     Handles mixed/malformed timestamps (e.g. MM:SS,mmm --> HH:MM:SS,mmm) by
#     parsing each side independently. Normalises all timestamps to HH:MM:SS,000
#     in the cleaned SRT output.
#     """
#     raw = path.read_text(encoding="utf-8")
#     blocks = re.split(r"\n\s*\n", raw.strip())
#     utterances = []

#     for block in blocks:
#         lines = [line.strip() for line in block.splitlines() if line.strip()]
#         if len(lines) < 3:
#             continue

#         # lines[0] = sequence number, lines[1] = timestamp range, lines[2+] = text
#         timestamp_line = lines[1]
#         text_lines = lines[2:]

#         start_sec = 0.0
#         end_sec = 0.0
#         timestamp_str = ""
#         raw_timestamp = timestamp_line

#         if "-->" in timestamp_line:
#             left, _, right = timestamp_line.partition("-->")
#             start_sec = _parse_srt_time(left)
#             end_sec = _parse_srt_time(right)
#             mins = int(start_sec) // 60
#             secs = int(start_sec) % 60
#             timestamp_str = f"{mins:02d}:{secs:02d}"
#             # Always normalise to canonical HH:MM:SS,000 in the cleaned SRT
#             raw_timestamp = f"{_sec_to_srt(start_sec)} --> {_sec_to_srt(end_sec)}"

#         # First text line may contain "Speaker: text"
#         speaker = ""
#         text_parts = []
#         for i, tline in enumerate(text_lines):
#             if i == 0:
#                 # Try to extract speaker label
#                 sp_match = re.match(r"^([^:]+?)\s*:\s*(.+)$", tline)
#                 if sp_match:
#                     speaker = sp_match.group(1).strip()
#                     if speaker.startswith("[") and speaker.endswith("]"):
#                         speaker = speaker[1:-1].strip()
#                     text_parts.append(sp_match.group(2).strip())
#                 else:
#                     text_parts.append(tline)
#             else:
#                 sp_match = re.match(r"^([^:]+?)\s*:\s*(.+)$", tline)
#                 if sp_match:
#                     sp_label = sp_match.group(1).strip()
#                     if sp_label.startswith("[") and sp_label.endswith("]"):
#                         sp_label = sp_label[1:-1].strip()
#                     if sp_label == speaker:
#                         text_parts.append(sp_match.group(2).strip())
#                     else:
#                         text_parts.append(tline)
#                 else:
#                     text_parts.append(tline)

#         if not text_parts:
#             continue

#         utterances.append({
#             "speaker": speaker,
#             "timestamp": timestamp_str,
#             "raw_timestamp": raw_timestamp,
#             "text": " ".join(text_parts),
#             "start_sec": start_sec,
#             "end_sec": end_sec,
#         })

#     return utterances


# def load_vtt_transcript(path: Path) -> list[dict]:
#     """
#     Parse a WebVTT file into utterance dicts.

#     Differences from SRT:
#     - Starts with a WEBVTT header line (and optional file metadata block).
#     - Cue IDs are optional and may be text, not just numbers.
#     - Timestamps use '.' as the millisecond separator and may omit the hours
#       component: MM:SS.mmm --> MM:SS.mmm.
#     - Cue blocks may carry inline tags (<b>, <i>, <c>, <timestamp>) that are
#       stripped before speaker extraction.
#     - NOTE and REGION blocks are skipped entirely.

#     Speaker labels are extracted the same way as in load_srt_transcript:
#     first text line of each cue must start with "Speaker: text".
#     """
#     raw = path.read_text(encoding="utf-8")

#     # Strip BOM that some exporters prepend
#     if raw.startswith("\ufeff"):
#         raw = raw[1:]

#     lines = raw.splitlines()

#     # Drop the WEBVTT header line and any file-level metadata that follows
#     # (metadata ends at the first blank line).
#     start = 0
#     if lines and lines[0].strip().upper().startswith("WEBVTT"):
#         start = 1
#         while start < len(lines) and lines[start].strip():
#             start += 1

#     content = "\n".join(lines[start:])
#     blocks = re.split(r"\n\s*\n", content.strip())

#     # Matches HH:MM:SS.mmm --> HH:MM:SS.mmm (hours optional for VTT)
#     ts_hms_re = re.compile(
#         r"(\d+):(\d{2}):(\d{2})[,.](\d+)\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d+)"
#     )
#     # Matches MM:SS.mmm --> MM:SS.mmm (no hours)
#     ts_ms_re = re.compile(
#         r"(\d{2}):(\d{2})[,.](\d+)\s*-->\s*(\d{2}):(\d{2})[,.](\d+)"
#     )
#     # VTT inline tags to strip from cue text
#     vtt_tag_re = re.compile(r"<[^>]+>")

#     utterances = []

#     for block in blocks:
#         block_lines = [line.strip() for line in block.splitlines() if line.strip()]
#         if not block_lines:
#             continue

#         # Skip NOTE and REGION blocks
#         if block_lines[0].upper().startswith(("NOTE", "REGION")):
#             continue

#         # Locate the timestamp line — it is the first line containing "-->"
#         ts_idx = next((i for i, l in enumerate(block_lines) if "-->" in l), None)
#         if ts_idx is None:
#             continue

#         timestamp_line = block_lines[ts_idx]
#         text_lines = block_lines[ts_idx + 1:]

#         # Parse timestamps (try HH:MM:SS first, fall back to MM:SS)
#         start_sec = 0.0
#         end_sec = 0.0
#         timestamp_str = ""

#         m = ts_hms_re.search(timestamp_line)
#         if m:
#             sh, sm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
#             eh, em, es = int(m.group(5)), int(m.group(6)), int(m.group(7))
#             start_sec = sh * 3600 + sm * 60 + ss
#             end_sec = eh * 3600 + em * 60 + es
#             timestamp_str = f"{sh * 60 + sm:02d}:{ss:02d}"
#         else:
#             m = ts_ms_re.search(timestamp_line)
#             if m:
#                 sm, ss = int(m.group(1)), int(m.group(2))
#                 em, es = int(m.group(4)), int(m.group(5))
#                 start_sec = sm * 60 + ss
#                 end_sec = em * 60 + es
#                 timestamp_str = f"{sm:02d}:{ss:02d}"

#         # Strip VTT inline tags from all text lines before further processing
#         text_lines = [vtt_tag_re.sub("", l).strip() for l in text_lines if l]
#         text_lines = [l for l in text_lines if l]

#         if not text_lines:
#             continue

#         # Extract speaker label using the same logic as load_srt_transcript
#         speaker = ""
#         text_parts = []
#         for i, tline in enumerate(text_lines):
#             if i == 0:
#                 sp_match = re.match(r"^([^:]+?)\s*:\s*(.+)$", tline)
#                 if sp_match:
#                     speaker = sp_match.group(1).strip()
#                     if speaker.startswith("[") and speaker.endswith("]"):
#                         speaker = speaker[1:-1].strip()
#                     text_parts.append(sp_match.group(2).strip())
#                 else:
#                     text_parts.append(tline)
#             else:
#                 sp_match = re.match(r"^([^:]+?)\s*:\s*(.+)$", tline)
#                 if sp_match:
#                     sp_label = sp_match.group(1).strip()
#                     if sp_label.startswith("[") and sp_label.endswith("]"):
#                         sp_label = sp_label[1:-1].strip()
#                     if sp_label == speaker:
#                         text_parts.append(sp_match.group(2).strip())
#                     else:
#                         text_parts.append(tline)
#                 else:
#                     text_parts.append(tline)

#         if not text_parts:
#             continue

#         utterances.append({
#             "speaker": speaker,
#             "timestamp": timestamp_str,
#             "text": " ".join(text_parts),
#             "start_sec": start_sec,
#             "end_sec": end_sec,
#         })

#     return utterances


# def compute_stats(utterances: list[dict], formatted: str) -> dict:
#     """
#     Compute call statistics from labeled utterances and the formatted transcript.

#     Duration: end_sec of last utterance minus start_sec of first (falls back to
#     start_sec of last utterance when end_sec is unavailable, e.g. JSON/txt inputs).
#     Token estimate uses the chars/4 heuristic (GPT/Claude average).
#     """
#     if not utterances:
#         return {}

#     # Use the true min/max across all utterances — guards against zero-timestamp
#     # entries that appear at the end of malformed SRT files.
#     all_starts = [u.get("start_sec", 0.0) for u in utterances]
#     all_ends = [u.get("end_sec", 0.0) or u.get("start_sec", 0.0) for u in utterances]
#     first_start = min(all_starts)
#     last_end = max(max(all_ends), max(all_starts))
#     duration_sec = max(0.0, last_end - first_start)

#     total_words = sum(len(utt["text"].split()) for utt in utterances)
#     total_chars = sum(len(utt["text"]) for utt in utterances)
#     # chars/4 is the standard approximation for Claude/GPT token counts
#     estimated_tokens = total_chars // 4

#     rep_words = sum(len(u["text"].split()) for u in utterances if u.get("role") == "SALES_REP")
#     cust_words = sum(len(u["text"].split()) for u in utterances if u.get("role") == "CUSTOMER")

#     mins = int(duration_sec) // 60
#     secs = int(duration_sec) % 60
#     duration_str = f"{mins}m {secs:02d}s"

#     return {
#         "duration_sec": duration_sec,
#         "duration_str": duration_str,
#         "total_words": total_words,
#         "rep_words": rep_words,
#         "customer_words": cust_words,
#         "total_chars": total_chars,
#         "estimated_tokens": estimated_tokens,
#     }


# def load_text_transcript(path: Path) -> list[dict]:
#     """
#     Parse a plain-text diarization file into utterance dicts.
#     Consecutive lines with no speaker label are appended to the previous utterance.
#     Lines that match no pattern are skipped with a warning.
#     """
#     raw = path.read_text(encoding="utf-8").splitlines()
#     utterances = []
#     skipped = 0

#     for lineno, line in enumerate(raw, 1):
#         line = line.strip()
#         if not line:
#             continue

#         matched = False
#         for pattern in DIARIZATION_PATTERNS:
#             m = pattern.match(line)
#             if m:
#                 groups = m.groupdict()
#                 utterances.append({
#                     "speaker": groups["speaker"].strip(),
#                     "timestamp": groups.get("timestamp", ""),
#                     "text": groups["text"].strip(),
#                     # start_sec will be parsed from timestamp if present
#                     "start_sec": _timestamp_to_sec(groups.get("timestamp", "")),
#                 })
#                 matched = True
#                 break

#         if not matched:
#             # Continuation line — append to last utterance if one exists
#             if utterances:
#                 utterances[-1]["text"] += " " + line
#             else:
#                 skipped += 1

#     if skipped:
#         print(f"Warning: {skipped} line(s) could not be parsed and were skipped.")

#     return utterances


# def _timestamp_to_sec(ts: str) -> float:
#     """Convert HH:MM:SS or MM:SS or SS to seconds. Returns 0.0 if unparseable."""
#     if not ts:
#         return 0.0
#     parts = ts.split(":")
#     try:
#         parts = [float(p) for p in parts]
#         if len(parts) == 3:
#             return parts[0] * 3600 + parts[1] * 60 + parts[2]
#         if len(parts) == 2:
#             return parts[0] * 60 + parts[1]
#         return parts[0]
#     except ValueError:
#         return 0.0


# # ---------------------------------------------------------------------------
# # Speaker labeling
# # ---------------------------------------------------------------------------

# def label_speakers(utterances: list[dict], rep_speaker, customer_name: str | None = None) -> list[dict]:
#     """
#     Normalize speaker tags to SALES_REP / CUSTOMER / SPEAKER_N.

#     For JSON transcripts: rep_speaker is an int (Google STT speaker_tag).
#     For text transcripts: rep_speaker is a string label (first speaker encountered).
#     """
#     # Collect unique speakers in order of first appearance
#     seen: list = []
#     for utt in utterances:
#         tag = utt["speaker"]
#         if tag not in seen:
#             seen.append(tag)

#     def is_customer_match(tag, name):
#         if not name:
#             return False
#         return str(tag).lower() == str(name).lower()

#     # Heuristic for picking the Sales Rep:
#     # 1. If a specific rep_speaker is provided and it's NOT the expected customer, use it.
#     # 2. Otherwise, pick the first speaker who is NOT the expected customer.
#     # 3. If everyone looks like the customer (unlikely), fallback to seen[0].
#     if rep_speaker in seen and not is_customer_match(rep_speaker, customer_name):
#         effective_rep = rep_speaker
#     else:
#         potential_reps = [s for s in seen if not is_customer_match(s, customer_name)]
#         if potential_reps:
#             effective_rep = potential_reps[0]
#         else:
#             effective_rep = seen[0] if seen else rep_speaker

#     # Determine effective customer: The first speaker who is not the effective rep,
#     # or the second speaker if tags are integers
#     effective_cust = None
#     for tag in seen:
#         if tag != effective_rep:
#             effective_cust = tag
#             break
            
#     if effective_cust is None and len(seen) > 1:
#         effective_cust = seen[1]

#     labeled = []
#     for utt in utterances:
#         tag = utt["speaker"]
#         if tag == effective_rep or tag == 0:
#             role = "SALES_REP" if tag != 0 else "UNKNOWN"
#         elif tag == effective_cust or (isinstance(tag, int) and tag != effective_rep):
#             role = "CUSTOMER"
#         else:
#             role = f"SPEAKER_{tag}"
#         labeled.append({**utt, "role": role})
#     return labeled


# # ---------------------------------------------------------------------------
# # Cleaning
# # ---------------------------------------------------------------------------

# def fuzzy_replace_entities(text: str, targets: list[str], cutoff: float = 0.60) -> str:
#     """
#     Replaces phonetic STT misspellings with the correct entity name using
#     a flexible sliding window (handles STT splitting 1 word into 2).
#     Preserves surrounding punctuation.
#     """
#     words = text.split()
#     if not len(words):
#         return text
    
#     corrected_words = words[:]
#     for target in targets:
#         target_words = len(target.split())
#         # Check windows of size: target_words, and target_words + 1 (for STT word splits)
#         for window_size in (target_words, target_words + 1):
#             for i in range(len(words) - window_size + 1):
#                 # Skip if already modified in a previous replacement
#                 if any(w == "" for w in corrected_words[i:i + window_size]):
#                     continue
                    
#                 raw_window = " ".join(words[i:i + window_size])
#                 # Strip punctuation for accurate phonetic comparison
#                 clean_window = re.sub(r'[^\w\s]', '', raw_window)
                
#                 # Ignore very short windows to prevent false positives on common words
#                 if len(clean_window) < 5:
#                     continue
                    
#                 similarity = difflib.SequenceMatcher(None, clean_window.lower(), target.lower()).ratio()
                
#                 if similarity >= cutoff:
#                     # Find trailing punctuation in the last word of the window to preserve it
#                     last_word = words[i + window_size - 1]
#                     punctuation = ""
#                     m = re.search(r'([^\w\s]+)$', last_word)
#                     if m:
#                         punctuation = m.group(1)
                        
#                     # Snap the entire window to the target name, reattach punctuation
#                     corrected_words[i] = target + punctuation
#                     for j in range(1, window_size):
#                         corrected_words[i + j] = ""

#     # Rejoin array, skipping the empty indices we collapsed
#     return " ".join(w for w in corrected_words if w)


# def apply_corrections(text: str, corrections: dict) -> str:
#     # 1. Exact/Regex corrections from JSON config
#     all_corrections = {
#         **corrections.get("institute_names", {}),
#         **corrections.get("program_names", {}),
#     }
#     for wrong, correct in all_corrections.items():
#         text = re.sub(rf"\b{re.escape(wrong)}\b", correct, text, flags=re.IGNORECASE)

#     # 2. Fuzzy phonetic normalization for critical entities (e.g., STT butchering "Visakhapatnam")
#     text = fuzzy_replace_entities(text, FUZZY_TARGETS, cutoff=0.60)

#     return text


# def strip_fillers(text: str, fillers: list[str]) -> str:
#     for filler in sorted(fillers, key=len, reverse=True):
#         text = re.sub(rf"\b{re.escape(filler)}\b[,\s]*", " ", text, flags=re.IGNORECASE)
#     return re.sub(r" {2,}", " ", text).strip()


# def _format_vtt_time(sec: float) -> str:
#     if sec is None:
#         sec = 0.0
#     hours = int(sec // 3600)
#     minutes = int((sec % 3600) // 60)
#     seconds = int(sec % 60)
#     milliseconds = int(round((sec - int(sec)) * 1000))
#     return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

# def format_cleaned_vtt(utterances: list[dict]) -> str:
#     """
#     Produce a valid VTT file from labeled utterances.
#     """
#     vtt_lines = ["WEBVTT\n"]
#     for utt in utterances:
#         start_str = _format_vtt_time(utt.get("start_sec", 0.0))
#         end_str = _format_vtt_time(utt.get("end_sec", 0.0))
#         role = utt.get("role", "Unknown")
#         text = utt.get("text", "")
        
#         vtt_lines.append(f"{start_str} --> {end_str}")
#         vtt_lines.append(f"[{role}]: {text}\n")
        
#     return "\n".join(vtt_lines)





# # ---------------------------------------------------------------------------
# # Entry point
# # ---------------------------------------------------------------------------

# def main():
#     if len(sys.argv) < 2:
#         print("Usage: python src/clean.py <transcript_file>  (.json or .txt/.text)")
#         sys.exit(1)

#     transcript_path = Path(sys.argv[1])
#     if not transcript_path.exists():
#         print(f"Error: file not found: {transcript_path}")
#         sys.exit(1)

#     suffix = transcript_path.suffix.lower()

#     if suffix == ".json":
#         utterances = load_json_transcript(transcript_path)
#         rep_speaker = int(os.environ.get("SALES_REP_SPEAKER", DEFAULT_REP_SPEAKER))
#         print(f"Input format: JSON (transcribe.py output)")
#     elif suffix in (".txt", ".text"):
#         utterances = load_text_transcript(transcript_path)
#         # For text transcripts, rep_speaker is the string label of the first speaker.
#         # Can be overridden via SALES_REP_SPEAKER env var (string match).
#         rep_speaker = os.environ.get("SALES_REP_SPEAKER", None)
#         if rep_speaker is None and utterances:
#             rep_speaker = utterances[0]["speaker"]
#         print(f"Input format: plain-text diarization")
#         print(f"Treating '{rep_speaker}' as SALES_REP")
#     elif suffix == ".srt":
#         utterances = load_srt_transcript(transcript_path)
#         rep_speaker = os.environ.get("SALES_REP_SPEAKER", None)
#         if rep_speaker is None and utterances:
#             rep_speaker = utterances[0]["speaker"]
#         print(f"Input format: SRT subtitle")
#         print(f"Treating '{rep_speaker}' as SALES_REP")
#     elif suffix == ".vtt":
#         utterances = load_vtt_transcript(transcript_path)
#         rep_speaker = os.environ.get("SALES_REP_SPEAKER", None)
#         if rep_speaker is None and utterances:
#             rep_speaker = utterances[0]["speaker"]
#         print(f"Input format: WebVTT")
#         print(f"Treating '{rep_speaker}' as SALES_REP")
#     else:
#         print(f"Error: unsupported file type '{suffix}'. Expected .json, .txt, .text, .srt, or .vtt")
#         sys.exit(1)

#     corrections = load_corrections()
#     fillers = corrections.get("filler_words", [])

#     utterances = label_speakers(utterances, rep_speaker)

#     for utt in utterances:
#         utt["text"] = apply_corrections(utt["text"], corrections)
#         utt["text"] = strip_fillers(utt["text"], fillers)

#     formatted = format_cleaned_vtt(utterances)

#     output_dir = Path("output")
#     output_dir.mkdir(exist_ok=True)

#     # Strip our own .transcript suffix if present
#     stem = transcript_path.stem.replace(".transcript", "")

#     out_vtt = output_dir / f"{stem}.cleaned.vtt"
#     out_vtt.write_text(formatted, encoding="utf-8")

#     print(f"Cleaned VTT saved:        {out_vtt}")

#     rep_lines = sum(1 for u in utterances if u["role"] == "SALES_REP")
#     cust_lines = sum(1 for u in utterances if u["role"] == "CUSTOMER")
#     print(f"SALES_REP utterances: {rep_lines} | CUSTOMER utterances: {cust_lines}")

#     # Derive the original speaker names from the labeled utterances.
#     # label_speakers preserves the raw 'speaker' field alongside the added 'role'.
#     rep_name = next(
#         (u["speaker"] for u in utterances if u.get("role") == "SALES_REP" and u.get("speaker")),
#         "Unknown",
#     )
#     customer_name = next(
#         (u["speaker"] for u in utterances if u.get("role") == "CUSTOMER" and u.get("speaker")),
#         "Unknown",
#     )

#     stats = compute_stats(utterances, formatted)
#     if stats:
#         print(f"STATS call_duration: {stats['duration_str']} ({int(stats['duration_sec'])}s)")
#         print(f"STATS total_words: {stats['total_words']} (rep: {stats['rep_words']}, customer: {stats['customer_words']})")
#         print(f"STATS total_chars: {stats['total_chars']}")
#         print(f"STATS estimated_transcript_tokens: {stats['estimated_tokens']}")
#     print(f"STATS sales_rep_name: {rep_name}")
#     print(f"STATS customer_name: {customer_name}")
#     print(f"STATS stt_file: {transcript_path}")


# if __name__ == "__main__":
#     main()

"""
Cleans a diarized transcript and outputs one file:
  - output/<stem>.cleaned.vtt  — WebVTT with normalized speaker labels, term
                                  corrections, fuzzy matches, and minimal filler
                                  removal; preserves original timing and structure.

Accepts three input formats:
  1. JSON  — our own *.transcript.json produced by transcribe.py
  2. Plain text — diarization exports from external tools (Otter.ai, Whisper,
                  Rev.ai, etc.) with speaker labels in common formats
  3. SRT — SubRip subtitle files with speaker labels in the text lines
  4. VTT — WebVTT subtitle files with optional inline tags

Cleaning applied to all formats:
  - Labels numeric/generic speaker tags as SALES_REP / CUSTOMER / SPEAKER_N
  - Applies term corrections from config/corrections.json
  - Applies fuzzy phonetic entity normalization for hard-to-transcribe institute names
  - Strips only true zero-content fillers (um, uh, hmm) — no semantic words

Usage:
    python src/clean.py <transcript_file>   (.json, .txt/.text, .srt, or .vtt)

Output:
    output/<stem>.cleaned.vtt
"""

import os
import sys
import json
import re
import difflib
from pathlib import Path


CORRECTIONS_PATH = Path("config/corrections.json")

# Heuristic: in Accredian outbound calls, speaker 1 initiates — they're the rep.
# Speaker 2 is the customer. Override by setting SALES_REP_SPEAKER env var.
DEFAULT_REP_SPEAKER = 1

# Entities for Fuzzy Phonetic Matching
# Add any high-priority, frequently misspelled names here.
# Tier 1 — Standard fuzzy targets (cutoff: 0.82)
# Short/well-known names that STT rarely mangles beyond recognition.
# High threshold prevents common words from false-matching.
FUZZY_TARGETS = [
    "Accredian",
    "E&ICT Academy IIT Kanpur",
    "IIT Hyderabad",
    "IIT Guwahati",
    "IIM Lucknow",
    "SP Jain School of Global Management",
    "XLRI Delhi",
    "XLRI",
    "SP Jain Global",
    "Jamshedpur",
    "IIM Ranchi",
    "Ranchi"
]

# Tier 2 — Hard phonetic targets (per-entry custom cutoff)
# Long, foreign-origin, or heavily distorted words that STT consistently
# mangles past what 0.82 can catch. Each entry is (canonical_form, cutoff).
# ONLY add words here that you have confirmed miss at the standard cutoff.
# Keep this list small and deliberate — every entry is a precision risk.
FUZZY_TARGETS_SOFT = [
    ("Visakhapatnam",     0.55),
    ("IIM Visakhapatnam", 0.55),
    ("Accredian",         0.62), 
    ("XLRI Jamshedpur",   0.62),
    ("Jamshedpur",        0.62),
    ("SP Jain",           0.62)

]

# Plain-text diarization patterns (tried in order, first match wins per line).
# Each pattern must have a named group 'speaker' and 'text'.
# Optional named group 'timestamp' is preserved if present.
DIARIZATION_PATTERNS = [
    # [00:01:23] Speaker 1: text   or   [01:23] Speaker 1: text
    re.compile(
        r"^\[(?P<timestamp>[\d:]+)\]\s*(?P<speaker>[^\:]+?)\s*:\s*(?P<text>.+)$"
    ),
    # Speaker 1 (00:01:23): text
    re.compile(
        r"^(?P<speaker>[^\(]+?)\s*\((?P<timestamp>[\d:]+)\)\s*:\s*(?P<text>.+)$"
    ),
    # Speaker 1: text   (no timestamp)
    re.compile(
        r"^(?P<speaker>(?:Speaker|SPEAKER|Rep|Agent|Customer|Caller|Sales)[^\:]*?)\s*:\s*(?P<text>.+)$",
        re.IGNORECASE,
    ),
    # S1: text  or  SP1: text
    re.compile(
        r"^(?P<speaker>S[Pp]?\d+)\s*:\s*(?P<text>.+)$"
    ),
]


def load_corrections() -> dict:
    if not CORRECTIONS_PATH.exists():
        print(f"Warning: corrections file not found at {CORRECTIONS_PATH}, skipping.")
        return {}
    return json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_json_transcript(path: Path) -> list[dict]:
    """Load utterances from our own *.transcript.json format."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if "utterances" not in data:
        raise ValueError(f"Expected 'utterances' key in JSON, not found in {path}")
    return data["utterances"]


def _parse_srt_time(s: str) -> float:
    """Parse one side of an SRT/VTT timestamp (HH:MM:SS,mmm or MM:SS,mmm)."""
    s = s.strip()
    m = re.match(r"(\d+):(\d{2}):(\d{2})[,.](\d+)", s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.match(r"(\d{1,2}):(\d{2})[,.](\d+)", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return 0.0


def _sec_to_srt(sec: float) -> str:
    """Format seconds as HH:MM:SS,000 for SRT output."""
    sec = int(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d},000"


def load_srt_transcript(path: Path) -> list[dict]:
    """
    Parse an SRT file into utterance dicts.

    Expected block format:
        <sequence>
        HH:MM:SS,mmm --> HH:MM:SS,mmm
        Speaker: text
        [continuation lines...]

    Handles mixed/malformed timestamps (e.g. MM:SS,mmm --> HH:MM:SS,mmm) by
    parsing each side independently. Normalises all timestamps to HH:MM:SS,000
    in the cleaned SRT output.
    """
    raw = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", raw.strip())
    utterances = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue

        # lines[0] = sequence number, lines[1] = timestamp range, lines[2+] = text
        timestamp_line = lines[1]
        text_lines = lines[2:]

        start_sec = 0.0
        end_sec = 0.0
        timestamp_str = ""
        raw_timestamp = timestamp_line

        if "-->" in timestamp_line:
            left, _, right = timestamp_line.partition("-->")
            start_sec = _parse_srt_time(left)
            end_sec = _parse_srt_time(right)
            mins = int(start_sec) // 60
            secs = int(start_sec) % 60
            timestamp_str = f"{mins:02d}:{secs:02d}"
            # Always normalise to canonical HH:MM:SS,000 in the cleaned SRT
            raw_timestamp = f"{_sec_to_srt(start_sec)} --> {_sec_to_srt(end_sec)}"

        # First text line may contain "Speaker: text"
        speaker = ""
        text_parts = []
        for i, tline in enumerate(text_lines):
            if i == 0:
                # Try to extract speaker label
                sp_match = re.match(r"^([^:]+?)\s*:\s*(.+)$", tline)
                if sp_match:
                    speaker = sp_match.group(1).strip()
                    if speaker.startswith("[") and speaker.endswith("]"):
                        speaker = speaker[1:-1].strip()
                    text_parts.append(sp_match.group(2).strip())
                else:
                    text_parts.append(tline)
            else:
                sp_match = re.match(r"^([^:]+?)\s*:\s*(.+)$", tline)
                if sp_match:
                    sp_label = sp_match.group(1).strip()
                    if sp_label.startswith("[") and sp_label.endswith("]"):
                        sp_label = sp_label[1:-1].strip()
                    if sp_label == speaker:
                        text_parts.append(sp_match.group(2).strip())
                    else:
                        text_parts.append(tline)
                else:
                    text_parts.append(tline)

        if not text_parts:
            continue

        utterances.append({
            "speaker": speaker,
            "timestamp": timestamp_str,
            "raw_timestamp": raw_timestamp,
            "text": " ".join(text_parts),
            "start_sec": start_sec,
            "end_sec": end_sec,
        })

    return utterances


def load_vtt_transcript(path: Path) -> list[dict]:
    """
    Parse a WebVTT file into utterance dicts.

    Differences from SRT:
    - Starts with a WEBVTT header line (and optional file metadata block).
    - Cue IDs are optional and may be text, not just numbers.
    - Timestamps use '.' as the millisecond separator and may omit the hours
      component: MM:SS.mmm --> MM:SS.mmm.
    - Cue blocks may carry inline tags (<b>, <i>, <c>, <timestamp>) that are
      stripped before speaker extraction.
    - NOTE and REGION blocks are skipped entirely.

    Speaker labels are extracted the same way as in load_srt_transcript:
    first text line of each cue must start with "Speaker: text".
    """
    raw = path.read_text(encoding="utf-8")

    # Strip BOM that some exporters prepend
    if raw.startswith("\ufeff"):
        raw = raw[1:]

    lines = raw.splitlines()

    # Drop the WEBVTT header line and any file-level metadata that follows
    # (metadata ends at the first blank line).
    start = 0
    if lines and lines[0].strip().upper().startswith("WEBVTT"):
        start = 1
        while start < len(lines) and lines[start].strip():
            start += 1

    content = "\n".join(lines[start:])
    blocks = re.split(r"\n\s*\n", content.strip())

    # Matches HH:MM:SS.mmm --> HH:MM:SS.mmm (hours optional for VTT)
    ts_hms_re = re.compile(
        r"(\d+):(\d{2}):(\d{2})[,.](\d+)\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d+)"
    )
    # Matches MM:SS.mmm --> MM:SS.mmm (no hours)
    ts_ms_re = re.compile(
        r"(\d{2}):(\d{2})[,.](\d+)\s*-->\s*(\d{2}):(\d{2})[,.](\d+)"
    )
    # VTT inline tags to strip from cue text
    vtt_tag_re = re.compile(r"<[^>]+>")

    utterances = []

    for block in blocks:
        block_lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not block_lines:
            continue

        # Skip NOTE and REGION blocks
        if block_lines[0].upper().startswith(("NOTE", "REGION")):
            continue

        # Locate the timestamp line — it is the first line containing "-->"
        ts_idx = next((i for i, l in enumerate(block_lines) if "-->" in l), None)
        if ts_idx is None:
            continue

        timestamp_line = block_lines[ts_idx]
        text_lines = block_lines[ts_idx + 1:]

        # Parse timestamps (try HH:MM:SS first, fall back to MM:SS)
        start_sec = 0.0
        end_sec = 0.0
        timestamp_str = ""

        m = ts_hms_re.search(timestamp_line)
        if m:
            sh, sm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
            eh, em, es = int(m.group(5)), int(m.group(6)), int(m.group(7))
            start_sec = sh * 3600 + sm * 60 + ss
            end_sec = eh * 3600 + em * 60 + es
            timestamp_str = f"{sh * 60 + sm:02d}:{ss:02d}"
        else:
            m = ts_ms_re.search(timestamp_line)
            if m:
                sm, ss = int(m.group(1)), int(m.group(2))
                em, es = int(m.group(4)), int(m.group(5))
                start_sec = sm * 60 + ss
                end_sec = em * 60 + es
                timestamp_str = f"{sm:02d}:{ss:02d}"

        # Strip VTT inline tags from all text lines before further processing
        text_lines = [vtt_tag_re.sub("", l).strip() for l in text_lines if l]
        text_lines = [l for l in text_lines if l]

        if not text_lines:
            continue

        # Extract speaker label using the same logic as load_srt_transcript
        speaker = ""
        text_parts = []
        for i, tline in enumerate(text_lines):
            if i == 0:
                sp_match = re.match(r"^([^:]+?)\s*:\s*(.+)$", tline)
                if sp_match:
                    speaker = sp_match.group(1).strip()
                    if speaker.startswith("[") and speaker.endswith("]"):
                        speaker = speaker[1:-1].strip()
                    text_parts.append(sp_match.group(2).strip())
                else:
                    text_parts.append(tline)
            else:
                sp_match = re.match(r"^([^:]+?)\s*:\s*(.+)$", tline)
                if sp_match:
                    sp_label = sp_match.group(1).strip()
                    if sp_label.startswith("[") and sp_label.endswith("]"):
                        sp_label = sp_label[1:-1].strip()
                    if sp_label == speaker:
                        text_parts.append(sp_match.group(2).strip())
                    else:
                        text_parts.append(tline)
                else:
                    text_parts.append(tline)

        if not text_parts:
            continue

        utterances.append({
            "speaker": speaker,
            "timestamp": timestamp_str,
            "text": " ".join(text_parts),
            "start_sec": start_sec,
            "end_sec": end_sec,
        })

    return utterances


def compute_stats(utterances: list[dict], formatted: str) -> dict:
    """
    Compute call statistics from labeled utterances and the formatted transcript.

    Duration: end_sec of last utterance minus start_sec of first (falls back to
    start_sec of last utterance when end_sec is unavailable, e.g. JSON/txt inputs).
    Token estimate uses the chars/4 heuristic (GPT/Claude average).
    """
    if not utterances:
        return {}

    # Use the true min/max across all utterances — guards against zero-timestamp
    # entries that appear at the end of malformed SRT files.
    all_starts = [u.get("start_sec", 0.0) for u in utterances]
    all_ends = [u.get("end_sec", 0.0) or u.get("start_sec", 0.0) for u in utterances]
    first_start = min(all_starts)
    last_end = max(max(all_ends), max(all_starts))
    duration_sec = max(0.0, last_end - first_start)

    total_words = sum(len(utt["text"].split()) for utt in utterances)
    total_chars = sum(len(utt["text"]) for utt in utterances)
    # chars/4 is the standard approximation for Claude/GPT token counts
    estimated_tokens = total_chars // 4

    rep_words = sum(len(u["text"].split()) for u in utterances if u.get("role") == "SALES_REP")
    cust_words = sum(len(u["text"].split()) for u in utterances if u.get("role") == "CUSTOMER")

    mins = int(duration_sec) // 60
    secs = int(duration_sec) % 60
    duration_str = f"{mins}m {secs:02d}s"

    return {
        "duration_sec": duration_sec,
        "duration_str": duration_str,
        "total_words": total_words,
        "rep_words": rep_words,
        "customer_words": cust_words,
        "total_chars": total_chars,
        "estimated_tokens": estimated_tokens,
    }


def load_text_transcript(path: Path) -> list[dict]:
    """
    Parse a plain-text diarization file into utterance dicts.
    Consecutive lines with no speaker label are appended to the previous utterance.
    Lines that match no pattern are skipped with a warning.
    """
    raw = path.read_text(encoding="utf-8").splitlines()
    utterances = []
    skipped = 0

    for lineno, line in enumerate(raw, 1):
        line = line.strip()
        if not line:
            continue

        matched = False
        for pattern in DIARIZATION_PATTERNS:
            m = pattern.match(line)
            if m:
                groups = m.groupdict()
                utterances.append({
                    "speaker": groups["speaker"].strip(),
                    "timestamp": groups.get("timestamp", ""),
                    "text": groups["text"].strip(),
                    # start_sec will be parsed from timestamp if present
                    "start_sec": _timestamp_to_sec(groups.get("timestamp", "")),
                })
                matched = True
                break

        if not matched:
            # Continuation line — append to last utterance if one exists
            if utterances:
                utterances[-1]["text"] += " " + line
            else:
                skipped += 1

    if skipped:
        print(f"Warning: {skipped} line(s) could not be parsed and were skipped.")

    return utterances


def _timestamp_to_sec(ts: str) -> float:
    """Convert HH:MM:SS or MM:SS or SS to seconds. Returns 0.0 if unparseable."""
    if not ts:
        return 0.0
    parts = ts.split(":")
    try:
        parts = [float(p) for p in parts]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0]
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Speaker labeling
# ---------------------------------------------------------------------------

def label_speakers(utterances: list[dict], rep_speaker, customer_name: str | None = None) -> list[dict]:
    """
    Normalize speaker tags to SALES_REP / CUSTOMER / SPEAKER_N.

    For JSON transcripts: rep_speaker is an int (Google STT speaker_tag).
    For text transcripts: rep_speaker is a string label (first speaker encountered).
    """
    # Collect unique speakers in order of first appearance
    seen: list = []
    for utt in utterances:
        tag = utt["speaker"]
        if tag not in seen:
            seen.append(tag)

    def is_customer_match(tag, name):
        if not name:
            return False
        return str(tag).lower() == str(name).lower()

    # Heuristic for picking the Sales Rep:
    # 1. If a specific rep_speaker is provided and it's NOT the expected customer, use it.
    # 2. Otherwise, pick the first speaker who is NOT the expected customer.
    # 3. If everyone looks like the customer (unlikely), fallback to seen[0].
    if rep_speaker in seen and not is_customer_match(rep_speaker, customer_name):
        effective_rep = rep_speaker
    else:
        potential_reps = [s for s in seen if not is_customer_match(s, customer_name)]
        if potential_reps:
            effective_rep = potential_reps[0]
        else:
            effective_rep = seen[0] if seen else rep_speaker

    # Determine effective customer: The first speaker who is not the effective rep,
    # or the second speaker if tags are integers
    effective_cust = None
    for tag in seen:
        if tag != effective_rep:
            effective_cust = tag
            break
            
    if effective_cust is None and len(seen) > 1:
        effective_cust = seen[1]

    labeled = []
    for utt in utterances:
        tag = utt["speaker"]
        if tag == effective_rep or tag == 0:
            role = "SALES_REP" if tag != 0 else "UNKNOWN"
        elif tag == effective_cust or (isinstance(tag, int) and tag != effective_rep):
            role = "CUSTOMER"
        else:
            role = f"SPEAKER_{tag}"
        labeled.append({**utt, "role": role})
    return labeled


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

def fuzzy_replace_entities(
    text: str,
    targets: list[str],
    cutoff: float = 0.70,
    soft_targets: list[tuple[str, float]] | None = None,
) -> str:
    """
    Replaces phonetic STT misspellings with the correct entity name using
    a flexible sliding window (handles STT splitting 1 word into 2).
    Preserves surrounding punctuation.

    Two-tier matching:
      - `targets` are matched at `cutoff` (default 0.82) — standard names.
      - `soft_targets` are (name, per_entry_cutoff) pairs for words that STT
        heavily distorts (e.g. "Visakhapatnam"). Each has its own lower cutoff
        but still enforces the uppercase and min-length guards.

    Guards applied to prevent false positives:
      1. First word of the candidate window must start uppercase — institute
         names are proper nouns; lowercase mid-sentence words are never matches.
      2. Window character length must be >= 60% of the target length — prevents
         short phrases (e.g. "fit what") from matching long institution names.
      3. Window expansion (+1 word) only for multi-word targets, to handle STT
         splitting a single spoken word across two tokens.
    """
    def _replace(words: list[str], target: str, threshold: float) -> list[str]:
        corrected = words[:]
        target_word_count = len(target.split())
        min_char_length = int(len(re.sub(r'[^\w\s]', '', target)) * 0.60)
        max_window = target_word_count + 1 if target_word_count >= 2 else target_word_count

        for window_size in range(target_word_count, max_window + 1):
            for i in range(len(words) - window_size + 1):
                # Guard 1: skip already-collapsed slots
                if any(w == "" for w in corrected[i:i + window_size]):
                    continue

                # Guard 2: first word must be a proper noun (starts uppercase)
                first_word = corrected[i].lstrip("\"'([")
                if not first_word or not first_word[0].isupper():
                    continue

                raw_window = " ".join(words[i:i + window_size])
                clean_window = re.sub(r'[^\w\s]', '', raw_window)

                # Guard 3: window must be long enough relative to target
                if len(clean_window) < min_char_length:
                    continue

                similarity = difflib.SequenceMatcher(
                    None, clean_window.lower(), target.lower()
                ).ratio()

                if similarity >= threshold:
                    last_word = words[i + window_size - 1]
                    punctuation = ""
                    m = re.search(r'([^\w\s]+)$', last_word)
                    if m:
                        punctuation = m.group(1)
                    corrected[i] = target + punctuation
                    for j in range(1, window_size):
                        corrected[i + j] = ""
        return corrected

    words = text.split()
    if not words:
        return text

    # Run Tier 1 — standard targets at the shared cutoff
    for target in targets:
        words = _replace(words, target, cutoff)

    # Run Tier 2 — hard phonetic targets at their individual cutoffs
    for target, per_entry_cutoff in (soft_targets or []):
        words = _replace(words, target, per_entry_cutoff)

    return " ".join(w for w in words if w)


def apply_corrections(text: str, corrections: dict) -> str:
    # 1. Exact/Regex corrections from JSON config
    all_corrections = {
        **corrections.get("institute_names", {}),
        **corrections.get("program_names", {}),
    }
    for wrong, correct in all_corrections.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", correct, text, flags=re.IGNORECASE)

    # 2. Fuzzy phonetic normalization for critical entities (e.g., STT butchering "Visakhapatnam")
    text = fuzzy_replace_entities(text, FUZZY_TARGETS, soft_targets=FUZZY_TARGETS_SOFT)

    return text


def strip_fillers(text: str, fillers: list[str]) -> str:
    for filler in sorted(fillers, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(filler)}\b[,\s]*", " ", text, flags=re.IGNORECASE)
    return re.sub(r" {2,}", " ", text).strip()


def _format_vtt_time(sec: float) -> str:
    if sec is None:
        sec = 0.0
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = int(sec % 60)
    milliseconds = int(round((sec - int(sec)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def format_cleaned_vtt(utterances: list[dict]) -> str:
    """
    Produce a valid VTT file from labeled utterances.
    """
    vtt_lines = ["WEBVTT\n"]
    for utt in utterances:
        start_str = _format_vtt_time(utt.get("start_sec", 0.0))
        end_str = _format_vtt_time(utt.get("end_sec", 0.0))
        role = utt.get("role", "Unknown")
        text = utt.get("text", "")
        
        vtt_lines.append(f"{start_str} --> {end_str}")
        vtt_lines.append(f"[{role}]: {text}\n")
        
    return "\n".join(vtt_lines)





# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/clean.py <transcript_file>  (.json or .txt/.text)")
        sys.exit(1)

    transcript_path = Path(sys.argv[1])
    if not transcript_path.exists():
        print(f"Error: file not found: {transcript_path}")
        sys.exit(1)

    suffix = transcript_path.suffix.lower()

    if suffix == ".json":
        utterances = load_json_transcript(transcript_path)
        rep_speaker = int(os.environ.get("SALES_REP_SPEAKER", DEFAULT_REP_SPEAKER))
        print(f"Input format: JSON (transcribe.py output)")
    elif suffix in (".txt", ".text"):
        utterances = load_text_transcript(transcript_path)
        # For text transcripts, rep_speaker is the string label of the first speaker.
        # Can be overridden via SALES_REP_SPEAKER env var (string match).
        rep_speaker = os.environ.get("SALES_REP_SPEAKER", None)
        if rep_speaker is None and utterances:
            rep_speaker = utterances[0]["speaker"]
        print(f"Input format: plain-text diarization")
        print(f"Treating '{rep_speaker}' as SALES_REP")
    elif suffix == ".srt":
        utterances = load_srt_transcript(transcript_path)
        rep_speaker = os.environ.get("SALES_REP_SPEAKER", None)
        if rep_speaker is None and utterances:
            rep_speaker = utterances[0]["speaker"]
        print(f"Input format: SRT subtitle")
        print(f"Treating '{rep_speaker}' as SALES_REP")
    elif suffix == ".vtt":
        utterances = load_vtt_transcript(transcript_path)
        rep_speaker = os.environ.get("SALES_REP_SPEAKER", None)
        if rep_speaker is None and utterances:
            rep_speaker = utterances[0]["speaker"]
        print(f"Input format: WebVTT")
        print(f"Treating '{rep_speaker}' as SALES_REP")
    else:
        print(f"Error: unsupported file type '{suffix}'. Expected .json, .txt, .text, .srt, or .vtt")
        sys.exit(1)

    corrections = load_corrections()
    fillers = corrections.get("filler_words", [])

    utterances = label_speakers(utterances, rep_speaker)

    for utt in utterances:
        utt["text"] = apply_corrections(utt["text"], corrections)
        utt["text"] = strip_fillers(utt["text"], fillers)

    formatted = format_cleaned_vtt(utterances)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # Strip our own .transcript suffix if present
    stem = transcript_path.stem.replace(".transcript", "")

    out_vtt = output_dir / f"{stem}.cleaned.vtt"
    out_vtt.write_text(formatted, encoding="utf-8")

    print(f"Cleaned VTT saved:        {out_vtt}")

    rep_lines = sum(1 for u in utterances if u["role"] == "SALES_REP")
    cust_lines = sum(1 for u in utterances if u["role"] == "CUSTOMER")
    print(f"SALES_REP utterances: {rep_lines} | CUSTOMER utterances: {cust_lines}")

    # Derive the original speaker names from the labeled utterances.
    # label_speakers preserves the raw 'speaker' field alongside the added 'role'.
    rep_name = next(
        (u["speaker"] for u in utterances if u.get("role") == "SALES_REP" and u.get("speaker")),
        "Unknown",
    )
    customer_name = next(
        (u["speaker"] for u in utterances if u.get("role") == "CUSTOMER" and u.get("speaker")),
        "Unknown",
    )

    stats = compute_stats(utterances, formatted)
    if stats:
        print(f"STATS call_duration: {stats['duration_str']} ({int(stats['duration_sec'])}s)")
        print(f"STATS total_words: {stats['total_words']} (rep: {stats['rep_words']}, customer: {stats['customer_words']})")
        print(f"STATS total_chars: {stats['total_chars']}")
        print(f"STATS estimated_transcript_tokens: {stats['estimated_tokens']}")
    print(f"STATS sales_rep_name: {rep_name}")
    print(f"STATS customer_name: {customer_name}")
    print(f"STATS stt_file: {transcript_path}")


if __name__ == "__main__":
    main()