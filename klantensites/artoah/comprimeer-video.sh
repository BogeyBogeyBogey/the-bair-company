#!/bin/bash
# === ARTOAH VIDEO COMPRESSIE ===
# Dit script comprimeert de hero-video van ~12MB naar ~2-3MB
#
# GEBRUIK:
# 1. Zet dit script in dezelfde map als Artoah.mp4
# 2. Open Terminal (Mac) of Command Prompt (Windows)
# 3. Navigeer naar de map: cd /pad/naar/map
# 4. Draai het script: bash comprimeer-video.sh
#
# VEREISTE: ffmpeg moet geïnstalleerd zijn
# - Mac: brew install ffmpeg
# - Windows: download van https://ffmpeg.org/download.html

echo "🎬 Artoah video compressie gestart..."

# Maak backup van origineel
cp Artoah.mp4 Artoah-origineel.mp4
echo "✅ Backup gemaakt: Artoah-origineel.mp4"

# Comprimeer: 720p, CRF 28, snelle preset
ffmpeg -i Artoah-origineel.mp4 \
  -vcodec libx264 \
  -crf 28 \
  -preset medium \
  -vf "scale=-2:720" \
  -an \
  -movflags +faststart \
  Artoah.mp4 \
  -y

echo ""
echo "✅ Video gecomprimeerd!"
echo "📊 Bestandsgrootte vergelijking:"
echo "   Origineel: $(du -h Artoah-origineel.mp4 | cut -f1)"
echo "   Nieuw:     $(du -h Artoah.mp4 | cut -f1)"
echo ""
echo "💡 Tip: Upload de nieuwe Artoah.mp4 naar je GitHub repo"
