#!/usr/bin/env python3
"""Text -> narration WAV with Chatterbox (resemble-ai/chatterbox).

  python scripts/voice.py "こんにちは、動画をコードで作ります。" -o work/voice.wav --lang ja
  python scripts/voice.py script.txt -o work/voice.wav --lang ja --ref my_voice_10s.wav

Japanese and other non-English text use the Multilingual V3 model.
Install: pip install chatterbox-tts   (a GPU is strongly recommended)
"""
import argparse
import pathlib


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", help="text, or path to a .txt file")
    ap.add_argument("-o", "--out", default="work/voice.wav")
    ap.add_argument("--lang", default="ja", help="language id (ja, en, fr, zh, ...)")
    ap.add_argument("--ref", help="10s reference clip for voice cloning (optional)")
    ap.add_argument("--device", default=None, help="cuda / mps / cpu (auto if omitted)")
    ap.add_argument("--exaggeration", type=float, default=0.5)
    args = ap.parse_args()

    import torch
    import torchaudio as ta

    device = args.device or ("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    p = pathlib.Path(args.text)
    text = p.read_text(encoding="utf-8").strip() if p.suffix == ".txt" and p.exists() else args.text

    if args.lang == "en":
        from chatterbox.tts import ChatterboxTTS

        model = ChatterboxTTS.from_pretrained(device=device)
        wav = model.generate(text, audio_prompt_path=args.ref, exaggeration=args.exaggeration)
    else:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        model = ChatterboxMultilingualTTS.from_pretrained(device=device, t3_model="v3")
        wav = model.generate(text, language_id=args.lang, audio_prompt_path=args.ref, exaggeration=args.exaggeration)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ta.save(str(out), wav, model.sr)
    print(out)


if __name__ == "__main__":
    main()
