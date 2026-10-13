#!/usr/bin/env python3
"""Descarga el audio de un video de YouTube y lo transcribe con Whisper large-v3 (Groq)."""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3"
CHUNK_SECONDS = 1800  # 30 min por trozo (~5 MB en opus 24 kbps, bajo el límite de 25 MB)

TMP = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
WORK = TMP / "work"
RESULT = TMP / "result.json"


def download(url):
    WORK.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp", "--no-playlist", "--no-progress",
        "-f", "bestaudio/best",
        "--write-info-json",
        "-o", str(WORK / "audio.%(ext)s"),
    ]
    cookies = os.environ.get("YT_COOKIES", "").strip()
    if cookies:
        path = TMP / "cookies.txt"
        path.write_text(cookies + "\n", encoding="utf-8")
        cmd += ["--cookies", str(path)]
    cmd += ["--", url]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        err = proc.stderr
        if "confirm you" in err and "bot" in err:
            raise RuntimeError(
                "YouTube bloqueó la descarga desde GitHub (pide confirmar que no eres un bot). "
                "Agrega tus cookies de YouTube en el secreto YT_COOKIES (ver README)."
            )
        last = [l for l in err.strip().splitlines() if "ERROR" in l] or err.strip().splitlines() or ["yt-dlp falló"]
        raise RuntimeError(last[-1].replace("ERROR: ", ""))

    info = json.loads((WORK / "audio.info.json").read_text(encoding="utf-8"))
    audio = next(
        p for p in WORK.iterdir()
        if p.name.startswith("audio.") and not p.name.endswith(".json")
    )
    return info, audio


def split(audio):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(audio),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "24k",
        "-f", "segment", "-segment_time", str(CHUNK_SECONDS), "-segment_format", "ogg",
        "-reset_timestamps", "1", str(WORK / "chunk_%03d.ogg"),
    ], check=True)
    return sorted(WORK.glob("chunk_*.ogg"))


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def groq_error(resp):
    try:
        return resp.json()["error"]["message"]
    except Exception:
        return resp.text[:300]


def transcribe(chunk, language):
    data = {"model": MODEL, "response_format": "verbose_json", "temperature": "0"}
    if language:
        data["language"] = language
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}

    for attempt in range(6):
        with chunk.open("rb") as f:
            resp = requests.post(
                GROQ_URL, headers=headers, data=data,
                files={"file": (chunk.name, f, "audio/ogg")}, timeout=600,
            )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503) and attempt < 5:
            try:
                wait = float(resp.headers.get("retry-after", ""))
            except ValueError:
                wait = 20 * (attempt + 1)
            if wait <= 900:
                print(f"Groq {resp.status_code}, reintentando en {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                continue
        break
    raise RuntimeError(f"Groq respondió {resp.status_code}: {groq_error(resp)}")


def paragraphs(segments):
    """Agrupa segmentos en párrafos por pausas largas o longitud."""
    paras, cur, chars, prev_end = [], [], 0, 0.0
    for s in segments:
        text = s["text"]
        if cur and (s["start"] - prev_end > 2.0 or (chars > 500 and cur[-1][-1:] in ".?!…")):
            paras.append(" ".join(cur))
            cur, chars = [], 0
        cur.append(text)
        chars += len(text)
        prev_end = s["end"]
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(paras)


def main():
    url = os.environ["VIDEO_URL"].strip()
    language = os.environ.get("LANGUAGE", "").strip()
    result = {
        "key": os.environ["KEY"],
        "nonce": os.environ["NONCE"],
        "url": url,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        if not os.environ.get("GROQ_API_KEY"):
            raise RuntimeError("Falta el secreto GROQ_API_KEY en el repositorio (ver README).")
        if language and not re.fullmatch(r"[a-z]{2,3}", language):
            raise RuntimeError(f"Idioma inválido: {language}")

        info, audio = download(url)
        chunks = split(audio)

        segments, detected, offset = [], None, 0.0
        for i, chunk in enumerate(chunks, 1):
            print(f"Transcribiendo parte {i}/{len(chunks)}", file=sys.stderr)
            res = transcribe(chunk, language)
            detected = detected or res.get("language")
            for s in res.get("segments", []):
                text = s.get("text", "").strip()
                # Descarta alucinaciones típicas de Whisper en silencios/música
                if not text or (s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -1.0):
                    continue
                segments.append({
                    "start": round(s["start"] + offset, 2),
                    "end": round(s["end"] + offset, 2),
                    "text": text,
                })
            offset += duration(chunk)

        result.update(
            title=info.get("title"),
            channel=info.get("channel") or info.get("uploader"),
            duration=info.get("duration"),
            language=language or detected,
            text=paragraphs(segments),
            segments=segments,
        )
    except Exception as e:  # el error se guarda para mostrarlo en la web
        result["error"] = str(e) or e.__class__.__name__

    RESULT.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
