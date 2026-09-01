"""
Deepgram Speech-to-Text service — async (non-blocking) interface.

Required environment variables
-------------------------------
  DEEPGRAM_API_KEY               — Deepgram API key.

Public API
----------
  submit_stt(audio_path) -> (operation_name, audio_path)
      Submit audio for transcription. Returns immediately without blocking.

  poll_stt(operation_name, audio_path) -> (done, utterances | None)
      Perform the transcription request via Deepgram.

  save_transcript(pipeline_id, audio_path, utterances) -> (transcript_path, sales_rep_name)
      Persist utterances to output and identify speakers.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Local formats sent to Deepgram.
SUPPORTED_DIRECT = {".flac", ".wav"}
SUPPORTED_VIA_FFMPEG = {".mp3", ".mp4", ".m4a", ".ogg", ".opus", ".webm"}

# GCS HTTPS public/signed URL prefix (if used as remote URL for Deepgram).
GCS_HTTPS_PREFIX = "https://storage.googleapis.com/"


def _is_remote_url(path: str) -> bool:
    """Return True if the path is a remote URL (http/https)."""
    return path.strip().startswith(("http://", "https://"))


def submit_stt(audio_path: str) -> tuple[str, str]:
    """
    Submit audio to Deepgram and return immediately.
    For Deepgram, we don't need a long-running operation ID from a submission step
    in the same way Google does, so we return a dummy ID and the path.
    """
    audio_path = audio_path.strip()
    return f"dg-{uuid.uuid4().hex}", audio_path


def poll_stt(operation_name: str, audio_path: str) -> tuple[bool, list[dict] | None]:
    """
    Execute the Deepgram STT request.
    """
    import httpx
    from src.transcribe import transcribe_deepgram
    
    try:
        # Handle remote HTTPS urls or local files
        if _is_remote_url(audio_path):
            api_key = os.getenv("DEEPGRAM_API_KEY")
            if not api_key:
                raise ValueError("DEEPGRAM_API_KEY not set.")
                
            url = "https://api.deepgram.com/v1/listen"
            params = {
                "model": "nova-3", 
                "smart_format": "true", 
                "diarize": "true", 
                "paragraphs": "true",
                "language": "en-IN"
            }
            headers = {
                "Authorization": f"Token {api_key}", 
                "Content-Type": "application/json"
            }
            
            with httpx.Client(timeout=600.0) as client:
                response = client.post(url, headers=headers, params=params, json={"url": audio_path})
            
            if response.status_code != 200:
                raise RuntimeError(f"Deepgram API failed [{response.status_code}]: {response.text}")
                
            data = response.json()
            alt = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]
            
            # Use Deepgram's native paragraphs feature for grouping
            paragraphs_data = alt.get("paragraphs", {}).get("paragraphs", [])
            
            utterances = []
            if paragraphs_data:
                for p in paragraphs_data:
                    utterances.append({
                        "speaker": p.get("speaker", 0) + 1,
                        "start_sec": p.get("start", 0.0),
                        "end_sec": p.get("end", 0.0),
                        "text": "".join(s.get("text", "") for s in p.get("sentences", [])).strip()
                    })
            else:
                # Fallback to word-level grouping if paragraphs missing
                words = alt.get("words", [])
                current_speaker = None
                current_words = []
                current_start = None
                previous_end = None

                for word in words:
                    speaker = word.get("speaker", 0) + 1
                    start = word["start"]
                    end = word["end"]
                    word_text = word.get("punctuated_word", word["word"])

                    if current_speaker is not None and speaker != current_speaker:
                        utterances.append({
                            "speaker": current_speaker,
                            "start_sec": current_start,
                            "end_sec": previous_end,
                            "text": " ".join(current_words),
                        })
                        current_words = [word_text]
                        current_start = start
                        current_speaker = speaker
                    else:
                        if current_speaker is None:
                            current_speaker = speaker
                            current_start = start
                        current_words.append(word_text)
                    previous_end = end
                
                if current_words:
                    utterances.append({
                        "speaker": current_speaker,
                        "start_sec": current_start,
                        "end_sec": previous_end,
                        "text": " ".join(current_words),
                    })
            
            return True, utterances
        else:
            # Local file
            provider = os.getenv("STT_PROVIDER", "deepgram").lower()
            if provider == "assemblyai":
                from src.transcribe import transcribe_assemblyai
                utterances = transcribe_assemblyai(Path(audio_path))
            else:
                utterances = transcribe_deepgram(Path(audio_path))
            return True, utterances
    except Exception as e:
        provider = os.getenv("STT_PROVIDER", "deepgram").upper()
        raise RuntimeError(f"{provider} STT failed: {e}")


def _format_vtt_time(sec: float) -> str:
    if sec is None:
        sec = 0.0
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = int(sec % 60)
    milliseconds = int(round((sec - int(sec)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _identify_speakers(utterances: list[dict]) -> dict:
    import json
    import os
    from openai import OpenAI
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {}
        
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    
    snippet = []
    for u in utterances[:20]:
        speaker = u.get("speaker", "Unknown")
        text = u.get("text", "")
        snippet.append(f"Speaker {speaker}: {text}")
    text_snippet = "\n".join(snippet)
    
    prompt = (
        "Analyze this call snippet and extract the true names of the speakers. "
        "Also identify which speaker is the Sales Rep (or agent) and which is the Customer. "
        "Return ONLY a JSON object mapping the speaker number to their extracted exact name. "
        "If a specific name cannot be found, use their role like 'Customer' or 'Sales Rep'. "
        "Include a 'sales_rep_id' field indicating the original speaker ID of the sales rep. "
        "Example format:\n"
        "{\n"
        '  "speaker_mapping": {\n'
        '    "1": "John",\n'
        '    "2": "Jane"\n'
        "  },\n"
        '  "sales_rep_id": "2"\n'
        "}\n\n"
        f"Call Snippet:\n{text_snippet}"
    )
    
    model = os.environ.get("OPENROUTER_DEFAULT_MODEL", "google/gemma-3-27b-it")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content or ""
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()
        return json.loads(text)
    except Exception as e:
        import traceback
        with open("debug.txt", "w") as f:
            f.write(traceback.format_exc())
        print(f"Speaker identification failed: {e}")
        return {}


def save_transcript(pipeline_id: str, audio_path: str, utterances: list[dict]) -> tuple[str, str | None]:
    """
    Persist utterances to output and return the path.
    Saves only the VTT format.
    """
    identity_info = _identify_speakers(utterances)
    speaker_mapping = identity_info.get("speaker_mapping", {})
    sales_rep_id = str(identity_info.get("sales_rep_id", ""))
    
    sales_rep_name = None
    if sales_rep_id and sales_rep_id in speaker_mapping:
        sales_rep_name = speaker_mapping[sales_rep_id]

    if speaker_mapping:
         for utt in utterances:
             orig_sp = str(utt.get("speaker"))
             mapped_name = speaker_mapping.get(orig_sp) or speaker_mapping.get(f"Speaker {orig_sp}")
             if mapped_name:
                 if "original_speaker_id" not in utt:
                     utt["original_speaker_id"] = utt["speaker"]
                 utt["speaker"] = mapped_name

    stem = Path(audio_path).stem
    output_dir = _PROJECT_ROOT / "data" / "output" / pipeline_id / "stt_result"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write VTT
    vtt_lines = ["WEBVTT\n"]
    for utt in utterances:
        start_str = _format_vtt_time(utt.get("start_sec", 0.0))
        end_str = _format_vtt_time(utt.get("end_sec", 0.0))
        speaker = utt.get("speaker", "Unknown")
        text = utt.get("text", "")
        
        vtt_lines.append(f"{start_str} --> {end_str}")
        vtt_lines.append(f"[{speaker}]: {text}\n")
        
    vtt_file = output_dir / f"{stem}.transcript.vtt"
    vtt_file.write_text("\n".join(vtt_lines), encoding="utf-8")

    # Write JSON for API consumption
    json_file = output_dir / f"{stem}.transcript.json"
    json_file.write_text(
        json.dumps({"utterances": utterances}, indent=2), 
        encoding="utf-8"
    )

    return str(vtt_file), sales_rep_name
