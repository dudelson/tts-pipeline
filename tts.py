#!/usr/bin/env python3
"""
Send a long text file (article/book length) to a self-hosted fish-speech
/v1/tts server reachable via an SSH tunnel at http://localhost:8080, then
stitch the resulting audio chunks into one file with ffmpeg.

Usage:
    1. In another terminal, open the tunnel to your vast.ai instance:
         ssh -N -L 8080:localhost:8080 -p <ssh_port> <user>@<vast_ai_host>
    2. pip install requests
    3. Make sure `ffmpeg` is installed locally (brew install ffmpeg / apt install ffmpeg)
    4. python3 tts_pipeline.py input.txt output.wav
"""

import re
import os
import sys
import shutil
import tempfile
import subprocess
import requests

API_URL = "http://localhost:8080/v1/tts"
MAX_CHARS = 1000          # safe chunk size per request; lower this if you see errors/timeouts
REQUEST_TIMEOUT = 600      # seconds, generation can be slow on long chunks
REFERENCE_ID = 'roger'     # set to a saved voice id (from /v1/references/list) for a consistent voice
AUDIO_FORMAT = "wav"       # wav/mp3/flac supported by fish-speech


def split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split on paragraphs first, then sentences, greedily packing chunks
    up to max_chars without cutting mid-sentence."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        if len(para) <= max_chars:
            candidate = (current + "\n\n" + para).strip() if current else para
            if len(candidate) <= max_chars:
                current = candidate
            else:
                flush()
                current = para
        else:
            # paragraph itself is too long, split into sentences
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sent in sentences:
                candidate = (current + " " + sent).strip() if current else sent
                if len(candidate) <= max_chars:
                    current = candidate
                else:
                    flush()
                    current = sent
    flush()
    return chunks


def synthesize_chunk(text: str, out_path: str) -> None:
    payload = {
        "text": text,
        "reference_id": REFERENCE_ID,
        "format": AUDIO_FORMAT,
        "streaming": False,
        "chunk_length": 200,
        "max_new_tokens": 2048,
    }
    resp = requests.post(API_URL, json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"TTS request failed ({resp.status_code}): {resp.text[:300]}")
    with open(out_path, "wb") as f:
        f.write(resp.content)


def concatenate_audio(chunk_paths: list[str], output_path: str) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH — install it before running this script.")

    list_file = output_path + ".filelist.txt"
    with open(list_file, "w") as f:
        for p in chunk_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output_path],
        check=True,
    )
    os.remove(list_file)


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 tts_pipeline.py <input.txt> <output.wav>")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = split_text_into_chunks(text, MAX_CHARS)
    print(f"Split input into {len(chunks)} chunk(s).")

    tmp_dir = tempfile.mkdtemp(prefix="tts_chunks_")
    chunk_paths = []
    try:
        for i, chunk in enumerate(chunks, start=1):
            chunk_path = os.path.join(tmp_dir, f"chunk_{i:04d}.{AUDIO_FORMAT}")
            print(f"[{i}/{len(chunks)}] Generating ({len(chunk)} chars)...")
            synthesize_chunk(chunk, chunk_path)
            chunk_paths.append(chunk_path)

        if len(chunk_paths) == 1:
            shutil.move(chunk_paths[0], output_path)
        else:
            print("Concatenating chunks with ffmpeg...")
            concatenate_audio(chunk_paths, output_path)

        print(f"Done. Final audio: {output_path}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
