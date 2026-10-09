#!/usr/bin/env bash
# BUS-1166 batch: apply overlays to all 4 agent videos
# Usage: bash scripts/bus1175_batch.sh
# Prerequisite: raw MP4 in assets/video/bus-1166/raw/

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RAW="$ROOT/assets/video/bus-1166/raw"
FINAL="$ROOT/assets/video/bus-1166/final"

mkdir -p "$FINAL"

apply_one() {
  local agent="$1"
  shift
  local sub1="$1" sub2="$2" sub3="$3"

  if [ ! -f "$RAW/$agent.mp4" ]; then
    echo "SKIP: $agent — raw/$agent.mp4 not found"
    return
  fi

  echo "=== $agent ==="
  python3 "$SCRIPT_DIR/bus1175_video_overlays.py" apply \
    --agent "$agent" \
    --in "$RAW/$agent.mp4" \
    --out "$FINAL/$agent.mp4" \
    --subtitles "$sub1" "$sub2" "$sub3" \
    --overwrite 2>&1 | sed 's/^/  /'

  # verify
  python3 "$SCRIPT_DIR/bus1175_video_overlays.py" verify \
    "$FINAL/$agent.mp4" \
    --raw "$RAW/$agent.mp4" \
    --agent "$agent" 2>&1 | sed 's/^/  [verify] /'
}

# Per-agent subtitle texts — ЗАПОЛНИТЬ UX/UI перед запуском
apply_one oracle  "Расскажи, что чувствуешь сейчас" "Исполнительнице порыв души важен" "Давай откроем карту чувств"
apply_one astro    "Звёзды говорят о переменах" "Венера в домах отношений" "Твой гороскоп недели готов"
apply_one tarot    "Карты видят твой вопрос" "Старый колода отвечает честно" "Три карты раскроют путь"
apply_one chiromant "Ладонь хранит историю" "Линия судьбы меняется" "Пришли фото — прочту"

echo ""
echo "=== ffprobe отчёт ==="
for agent in oracle astro tarot chiromant; do
  if [ -f "$FINAL/$agent.mp4" ]; then
    ffprobe -v quiet -print_format json \
      -show_streams -show_format "$FINAL/$agent.mp4" | \
      python3 -c "
import json,sys
d=json.load(sys.stdin)
s=next(s for s in d['streams'] if s['codec_type']=='video')
f=d['format']
print(f'$agent: {s[\"width\"]}x{s[\"height\"]} {f[\"duration\"]}s codec={s[\"codec_name\"]} crf=18')
"
  fi
done
