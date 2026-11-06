#!/usr/bin/env bash
# Final mux with FFmpeg: video + narration (+ optional BGM) + burned-in subtitles.
#
#   scripts/finish.sh out/hyperframes.mp4 work/voice.wav work/voice.srt out/final.mp4 [bgm.mp3]
#
# BGM is ducked to 15% under the narration. Japanese subtitles need a CJK font
# (e.g. apt-get install fonts-noto-cjk); override with SUB_FONT="Noto Sans CJK JP".
set -euo pipefail
video=$1 voice=$2 srt=$3 out=$4 bgm=${5:-}
font=${SUB_FONT:-Noto Sans CJK JP}
style="FontName=${font},FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,MarginV=40"
mkdir -p "$(dirname "$out")"

if [[ -n $bgm ]]; then
  ffmpeg -y -i "$video" -i "$voice" -stream_loop -1 -i "$bgm" \
    -filter_complex "[2:a]volume=0.15[b];[1:a][b]amix=inputs=2:duration=first:dropout_transition=0[a];[0:v]subtitles='${srt}':force_style='${style}'[v]" \
    -map "[v]" -map "[a]" -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest "$out"
else
  ffmpeg -y -i "$video" -i "$voice" \
    -filter_complex "[0:v]subtitles='${srt}':force_style='${style}'[v]" \
    -map "[v]" -map 1:a -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest "$out"
fi
echo "$out"
