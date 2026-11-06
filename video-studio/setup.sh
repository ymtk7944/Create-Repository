#!/usr/bin/env bash
# Video Studio setup: installs the 14-repository AI video stack in tiers.
#
#   ./setup.sh            # core + skills (light, no GPU needed)
#   ./setup.sh all        # everything below
#   ./setup.sh core       # FFmpeg check, yt-dlp, faster-whisper, npm deps (HyperFrames/Remotion/GSAP/three.js)
#   ./setup.sh skills     # Claude Code skills: HyperFrames, impeccable, anthropics/skills (video-related subset)
#   ./setup.sh voice      # chatterbox TTS (PyTorch; GPU recommended)
#   ./setup.sh 3d         # Blender check + mcp-for-blender addon/MCP setup
#   ./setup.sh comfy      # ComfyUI into vendor/ComfyUI (GPU)
#   ./setup.sh src        # shallow-clone all 14 repositories into vendor/src for reading
#
# Re-runnable. Python packages go into ./.venv (uv if available, else python -m venv).
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD
say() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

py_env() {
  if [[ ! -x .venv/bin/python ]]; then
    if have uv; then uv venv -q --python 3.11 .venv || uv venv -q .venv; else python3 -m venv .venv; fi
  fi
}
pip_i() { if have uv; then uv pip install -q --python .venv/bin/python "$@"; else .venv/bin/pip install -q "$@"; fi; }

core() {
  say "FFmpeg"
  if have ffmpeg; then ffmpeg -version | head -1; else
    echo "FFmpeg not found. Install: brew install ffmpeg / sudo apt-get install ffmpeg / winget install Gyan.FFmpeg"; fi
  say "Node packages (hyperframes, remotion, gsap, three)"
  have node || { echo "Node.js 22+ is required"; exit 1; }
  npm install --no-audit --no-fund
  say "Python: yt-dlp, faster-whisper"
  py_env
  pip_i yt-dlp faster-whisper
  .venv/bin/yt-dlp --version
}

skills() {
  say "HyperFrames skills"
  npx --yes hyperframes skills update || echo "(skip) hyperframes skills update failed"
  say "impeccable (design skill + hook)"
  npx --yes impeccable install --providers=claude --scope=project || echo "(skip) impeccable install failed"
  say "anthropics/skills (frontend-design, canvas-design, algorithmic-art, theme-factory)"
  tmp=$(mktemp -d)
  if git clone -q --depth 1 https://github.com/anthropics/skills "$tmp/skills"; then
    mkdir -p .claude/skills
    for s in frontend-design canvas-design algorithmic-art theme-factory; do
      [[ -d $tmp/skills/skills/$s ]] && rm -rf ".claude/skills/$s" && cp -r "$tmp/skills/skills/$s" .claude/skills/
    done
  fi
  rm -rf "$tmp"
  echo "Remotion skills (optional): npx skills add remotion-dev/skills"
}

voice() {
  say "chatterbox TTS"
  py_env
  pip_i chatterbox-tts
  echo "Note: Chatterbox is archived (no longer maintained) but MIT-licensed and usable."
}

threed() {
  say "Blender"
  if have blender; then blender --version | head -1; else
    echo "Blender not found. Download: https://www.blender.org/download/  (or: sudo snap install blender --classic)"; fi
  say "mcp-for-blender (Blender addon + MCP config for Claude)"
  have uvx || { echo "uv is required: curl -LsSf https://astral.sh/uv/install.sh | sh"; return; }
  uvx mcp-for-blender setup || echo "(skip) run 'uvx mcp-for-blender setup' manually"
  echo "This folder's .mcp.json already registers 'blender' and 'chrome-devtools' for Claude Code."
}

comfy() {
  say "ComfyUI"
  mkdir -p vendor
  [[ -d vendor/ComfyUI ]] || git clone -q --depth 1 https://github.com/Comfy-Org/ComfyUI vendor/ComfyUI
  (cd vendor/ComfyUI && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt)
  echo "Start: vendor/ComfyUI/.venv/bin/python vendor/ComfyUI/main.py  (http://127.0.0.1:8188)"
  echo "Put models under vendor/ComfyUI/models/ (checkpoints, vae, ...)."
}

src() {
  say "Shallow-cloning source of all 14 repositories into vendor/src"
  mkdir -p vendor/src
  python3 -c 'import json;[print(r["repo"]) for r in json.load(open("repos.json"))["repos"]]' | while read -r r; do
    d=vendor/src/${r#*/}
    if [[ -d $d ]]; then echo "skip $r"; else git clone -q --depth 1 "https://github.com/$r" "$d" && echo "ok   $r"; fi
  done
}

case ${1:-default} in
  default) core; skills ;;
  all) core; skills; voice; threed; comfy ;;
  core) core ;; skills) skills ;; voice) voice ;; 3d) threed ;; comfy) comfy ;; src) src ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
say "done"
