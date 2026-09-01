"""
Transcribes an audio file using Deepgram.

Usage:
    python src/transcribe.py <audio_file_path>

Output:
    output/<basename>.transcript.json
"""

import sys
import os
import json
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
import httpx

load_dotenv()

SUPPORTED_DIRECT = {".flac", ".wav"}
SUPPORTED_VIA_FFMPEG = {".mp3", ".mp4", ".m4a", ".ogg", ".opus", ".webm"}

SAMPLE_RATE = 16000
LANGUAGE = "en-IN"  
MAX_SPEAKERS = 3

def convert_to_flac(audio_path: Path) -> Path:
    """Convert audio to mono 16kHz FLAC using ffmpeg."""
    out_path = Path(tempfile.mktemp(suffix=".flac"))
    cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",       # mono
        "-c:a", "flac",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed:\n{result.stderr}")
    return out_path


def transcribe_deepgram(audio_path: Path) -> list[dict]:
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY environment variable not set.")

    url = "https://api.deepgram.com/v1/listen"
    params = {
        "model": "nova-3",
        "smart_format": "true",
        "diarize": "true",
        "paragraphs": "true",
        "language": "en-IN"
    }
    headers = {
        "Authorization": f"Token {api_key}"
    }

    print(f"Sending {audio_path.name} to Deepgram Nova-3...")
    audio_bytes = audio_path.read_bytes()

    with httpx.Client(timeout=600.0) as client:
        response = client.post(url, headers=headers, params=params, content=audio_bytes)

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

    return utterances


def transcribe_assemblyai(audio_path: Path) -> list[dict]:
    import time
    import httpx
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY environment variable not set.")
        
    headers = {
        "authorization": api_key,
    }
    
    # 1. Upload audio
    print(f"Uploading {audio_path.name} to AssemblyAI...")
    upload_url = "https://api.assemblyai.com/v2/upload"
    
    def read_file(path, chunk_size=5242880):
        with open(path, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                yield data

    with httpx.Client(timeout=600.0) as client:
        upload_response = client.post(upload_url, headers=headers, content=read_file(audio_path))
        
    if upload_response.status_code != 200:
        raise RuntimeError(f"AssemblyAI upload failed: {upload_response.text}")
        
    audio_url = upload_response.json()["upload_url"]
    
    # 2. Submit transcription
    print("Submitting transcription to AssemblyAI...")
    transcript_url = "https://api.assemblyai.com/v2/transcript"
    transcript_request = {
        "audio_url": audio_url,
        "speaker_labels": True,
        "language_code": "en_us"
    }
    
    with httpx.Client(timeout=600.0) as client:
        submit_response = client.post(transcript_url, json=transcript_request, headers=headers)
        
    if submit_response.status_code != 200:
        raise RuntimeError(f"AssemblyAI submit failed: {submit_response.text}")
        
    transcript_id = submit_response.json()["id"]
    
    # 3. Poll for completion
    polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    print("Polling AssemblyAI for transcription completion...")
    while True:
        with httpx.Client(timeout=600.0) as client:
            poll_response = client.get(polling_endpoint, headers=headers)
        poll_data = poll_response.json()
        status = poll_data["status"]
        if status == "completed":
            break
        elif status == "error":
            raise RuntimeError(f"AssemblyAI transcription failed: {poll_data['error']}")
        time.sleep(3)
        
    utterances = []
    for u in poll_data.get("utterances", []):
        sp_char = u.get("speaker", "A")
        try:
            sp = ord(sp_char) - ord('A') + 1
        except:
            sp = sp_char
            
        utterances.append({
            "speaker": sp,
            "start_sec": u["start"] / 1000.0,
            "end_sec": u["end"] / 1000.0,
            "text": u["text"]
        })
        
    return utterances


def transcribe(audio_path: Path) -> list[dict]:
    provider = os.getenv("STT_PROVIDER", "deepgram").lower()
    if provider == "assemblyai":
        return transcribe_assemblyai(audio_path)
    else:
        return transcribe_deepgram(audio_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python src/transcribe.py <audio_file_path>")
        sys.exit(1)

    audio_path = Path(sys.argv[1])
    if not audio_path.exists():
        print(f"Error: file not found: {audio_path}")
        sys.exit(1)

    provider = os.getenv("STT_PROVIDER", "deepgram").upper()
    print(f"Using STT Provider: {provider}")
    utterances = transcribe(audio_path)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    out_file = output_dir / f"{audio_path.stem}.transcript.json"

    out_file.write_text(
        json.dumps({"audio_file": str(audio_path), "provider": provider.lower(), "utterances": utterances}, indent=2),
        encoding="utf-8",
    )

    print(f"Transcript saved: {out_file}")
    print(f"Total utterances: {len(utterances)}")
    speakers = {u["speaker"] for u in utterances}
    print(f"Speakers detected: {sorted(speakers)}")


if __name__ == "__main__":
    main()
