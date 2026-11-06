#!/usr/bin/env bash
# Download reference footage / audio with yt-dlp. Only use material you have the rights to.
#   scripts/fetch.sh <url> [out_dir]          -> best mp4
#   AUDIO_ONLY=1 scripts/fetch.sh <url>        -> m4a
set -euo pipefail
url=$1 dir=${2:-work/sources}
mkdir -p "$dir"
if [[ ${AUDIO_ONLY:-0} == 1 ]]; then
  yt-dlp -f bestaudio -x --audio-format m4a -o "$dir/%(title)s.%(ext)s" "$url"
else
  yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" --merge-output-format mp4 -o "$dir/%(title)s.%(ext)s" "$url"
fi
