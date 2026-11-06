#!/usr/bin/env python3
"""Audio/video -> SRT (and word-level JSON) with faster-whisper (SYSTRAN/faster-whisper).

  python scripts/subtitles.py work/voice.wav -o work/voice.srt --lang ja
  python scripts/subtitles.py input.mp4 -o work/input.srt --model large-v3

Install: pip install faster-whisper
"""
import argparse
import json
import pathlib


def ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("-o", "--out", default=None, help="output .srt (default: next to input)")
    ap.add_argument("--lang", default=None, help="language code, e.g. ja (auto-detect if omitted)")
    ap.add_argument("--model", default="small", help="tiny / base / small / medium / large-v3 / turbo")
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    model = WhisperModel(args.model, device=args.device, compute_type="default")
    segments, info = model.transcribe(args.media, language=args.lang, word_timestamps=True, vad_filter=True)

    out = pathlib.Path(args.out or pathlib.Path(args.media).with_suffix(".srt"))
    out.parent.mkdir(parents=True, exist_ok=True)
    words, lines = [], []
    for i, seg in enumerate(segments, 1):
        lines.append(f"{i}\n{ts(seg.start)} --> {ts(seg.end)}\n{seg.text.strip()}\n")
        words += [{"text": w.word, "start": w.start, "end": w.end} for w in (seg.words or [])]
    out.write_text("\n".join(lines), encoding="utf-8")
    # word-level timings, usable for kinetic captions in HyperFrames / Remotion
    out.with_suffix(".words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out} ({info.language}, {info.duration:.1f}s)")


if __name__ == "__main__":
    main()
