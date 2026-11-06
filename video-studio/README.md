# Video Studio — 14 OSS repositories, everything for AI video built in code

A kit that brings voice, subtitles, 3D, motion, and rendering together, **all as code and all free (OSS)**.
Open this folder in Claude Code and just ask, for example, "make a 15-second product intro video".

```
                ┌─────────── Materials ───────────┐
 yt-dlp ──────▶ │ reference footage / audio        │
 ComfyUI ─────▶ │ generated images / video         │
 Blender ─────▶ │ 3D renders (← mcp-for-blender)   │
 chatterbox ──▶ │ narration (TTS)                  │
                └──────────────┬───────────────────┘
                               ▼
 HyperFrames (HTML) / Remotion (React)  +  GSAP / three.js   ← impeccable · skills (design quality)
                               │           ↑ chrome-devtools-mcp (browser check)
                               ▼
 faster-whisper (subtitles SRT / word timings) ─▶ FFmpeg (audio mix, subtitle burn-in, encode) ─▶ final.mp4
```

## The 14 repositories

| # | Repository | Role | Install |
|---|---|---|---|
| 1 | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | Write in HTML → render MP4. Built for agents | npm (`hyperframes`) |
| 2 | [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | Write video in React → render MP4 | npm (`remotion`) |
| 3 | [greensock/GSAP](https://github.com/greensock/GSAP) | Motion (timeline animation) | npm (`gsap`) |
| 4 | [mrdoob/three.js](https://github.com/mrdoob/three.js) | Web 3D (embedded in HTML/React) | npm (`three`) |
| 5 | [blender/blender](https://github.com/blender/blender) | Full 3D modelling and rendering | official installer |
| 6 | [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender) | Let Claude drive Blender (MCP) | `uvx mcp-for-blender` |
| 7 | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) | Image and video generation (node-based) | `./setup.sh comfy` |
| 8 | [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) | Voice synthesis (supports Japanese, voice cloning) | `pip install chatterbox-tts` |
| 9 | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech recognition → subtitles | `pip install faster-whisper` |
| 10 | [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | Encoding, compositing, subtitle burn-in | OS package |
| 11 | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | Fetch footage / audio | `pip install yt-dlp` |
| 12 | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) | Let Claude check the browser (preview checks) | `.mcp.json` |
| 13 | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | Design quality (catches and fixes "AI slop") | `npx impeccable install` |
| 14 | [anthropics/skills](https://github.com/anthropics/skills) | Claude agent skills (frontend-design etc.) | `./setup.sh skills` |

The machine-readable list is in [`repos.json`](repos.json).

## Setup

Requirements: Node.js 22+, Python 3.10+, FFmpeg, (recommended) [uv](https://docs.astral.sh/uv/)

```bash
cd video-studio
./setup.sh            # light: FFmpeg check, yt-dlp, faster-whisper, npm deps, Claude skills
./setup.sh voice      # chatterbox (PyTorch; GPU recommended)
./setup.sh 3d         # Blender check + mcp-for-blender
./setup.sh comfy      # ComfyUI (GPU)
./setup.sh src        # shallow-clone the source of all 14 into vendor/src (for reading)
./setup.sh all        # everything except src
```

The MCP servers (`blender` / `chrome-devtools`) are registered in this folder's [`.mcp.json`](.mcp.json).
Launch `claude` inside `video-studio/` and they're available after you approve them.

## Usage (step by step)

```bash
# 1) Visuals: HyperFrames (HTML + GSAP)
npx hyperframes check  examples/hyperframes
npx hyperframes render examples/hyperframes -o out/video.mp4
#    or Remotion (React)
npm run remotion:render

# 2) Voice: chatterbox (Japanese)
.venv/bin/python scripts/voice.py "Voice, subtitles, 3D — all in code." -o work/voice.wav --lang ja

# 3) Subtitles: faster-whisper → SRT + word-timing JSON (can also be used for kinetic captions)
.venv/bin/python scripts/subtitles.py work/voice.wav -o work/voice.srt --lang ja --model large-v3

# 4) Finish: FFmpeg (narration + BGM ducking + subtitle burn-in)
scripts/finish.sh out/video.mp4 work/voice.wav work/voice.srt out/final.mp4 bgm.mp3

# Extras
blender -b -P scripts/blender_turntable.py -- --label "FFmpeg" --out out/blender/   # 3D turntable
scripts/fetch.sh <URL>                                                              # fetch footage (only material you have rights to)
```

Japanese subtitles need a CJK font (`apt-get install fonts-noto-cjk` / on macOS, specify a font name like `SUB_FONT="Hiragino Sans"`).

## Sample prompts for Claude Code

- "Using /hyperframes, make a 15-second vertical video introducing the 14 tools. Read the narration with chatterbox and finish with burned-in subtitles"
- "Use Blender MCP to build a cute rounded character, then render a turntable into out/blender"
- "Check the HyperFrames preview with chrome-devtools and fix any design flaws with impeccable"

## Layout

```
video-studio/
├── README.md / CLAUDE.md      # this file / instructions for the agent
├── repos.json                 # the 14 repositories
├── setup.sh                   # tiered installer
├── .mcp.json                  # blender + chrome-devtools MCP
├── package.json               # hyperframes / remotion / gsap / three
├── examples/
│   ├── hyperframes/           # HTML+GSAP sample (14 products → TOTAL $0.00)
│   └── remotion/              # React sample
└── scripts/
    ├── voice.py               # chatterbox TTS
    ├── subtitles.py           # faster-whisper → SRT/JSON
    ├── finish.sh              # FFmpeg final mux
    ├── fetch.sh               # yt-dlp
    └── blender_turntable.py   # headless Blender render
```

## Notes

- **Chatterbox** was archived in August 2026 (no further updates; still MIT-licensed and usable).
- **ComfyUI / chatterbox / Blender rendering** realistically need a GPU.
- Use **yt-dlp** only for footage you have the rights to or that is explicitly licensed.
- Check each repository's license (MIT / Apache-2.0 / GPL etc.) individually. Blender and FFmpeg are GPL/LGPL.
