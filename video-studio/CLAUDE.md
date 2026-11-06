# Video Studio — agent notes

AI video production kit built from 14 OSS repos. See README.md for the full map.

## Pipeline (default order)
1. Visuals: HyperFrames (`examples/hyperframes`, HTML + GSAP) unless the user asks for React → Remotion (`examples/remotion`).
   Use the `/hyperframes` skills when installed; always run `npx hyperframes check <dir>` and look at
   `npx hyperframes snapshot` frames before rendering.
2. 3D: three.js inside the composition for simple scenes; Blender (`scripts/blender_turntable.py`, or the
   `blender` MCP server for interactive modelling) for hero assets → render to video, embed as `<video>`.
3. Voice: `scripts/voice.py` (chatterbox; `--lang ja` for Japanese).
4. Subtitles: `scripts/subtitles.py` (faster-whisper) → `.srt` + `.words.json` (word timings for kinetic captions).
5. Finish: `scripts/finish.sh` (FFmpeg mux, BGM ducking, subtitle burn-in).
6. QA: `chrome-devtools` MCP on the preview; impeccable for design critique.

## Rules
- Compositions must be deterministic: no `Math.random()` / `Date.now()` / network fetches. Ship JS libs
  locally (see `examples/hyperframes/assets/gsap.min.js`) so renders work offline.
- Text in frames ≥ 28px, contrast ≥ 4.5:1 (`hyperframes check` enforces this).
- Outputs go to `out/`, intermediates to `work/` (both git-ignored).
- Python tools run from `.venv/` (`./setup.sh` creates it).
- yt-dlp: only material the user has rights to.
