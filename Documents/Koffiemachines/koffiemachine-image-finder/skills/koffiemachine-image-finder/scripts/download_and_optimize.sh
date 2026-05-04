#!/bin/bash
# ============================================================================
# Koffiemachine Image Finder — Download & Optimize Script
# ============================================================================
# Gebruik: bash download_and_optimize.sh <image-url> <output-naam> [categorie]
#
# Voorbeelden:
#   bash download_and_optimize.sh "https://cdn.shopify.com/image.jpg" "jura-z10" "volautomaten"
#   bash download_and_optimize.sh "https://images.philips.com/img.webp" "philips-3300-lattego" "volautomaten"
#   bash download_and_optimize.sh "https://sageappliances.com/img.jpg" "sage-oracle-jet" "espressomachines"
#
# Het script:
# 1. Downloadt de afbeelding met correcte headers
# 2. Valideert of het echt een afbeelding is
# 3. Converteert indien nodig (webp/avif → jpg)
# 4. Resize naar 800x800 (main) en 400x400 (thumbnail)
# 5. Maakt een WebP-versie
# 6. Organiseert in de juiste mappenstructuur
# ============================================================================

set -e

# --- Configuratie ---
OUTPUT_BASE="./images"
MAIN_SIZE="800x800"
THUMB_SIZE="400x400"
JPG_QUALITY=85
WEBP_QUALITY=80
THUMB_QUALITY=80
MIN_FILE_SIZE=5000  # Minimum 5KB — anders is het waarschijnlijk een placeholder

# --- Kleuren voor output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Input validatie ---
if [ -z "$1" ] || [ -z "$2" ]; then
    echo -e "${RED}Gebruik: $0 <image-url> <output-naam> [categorie]${NC}"
    echo ""
    echo "  <image-url>    De URL van de afbeelding"
    echo "  <output-naam>  Bestandsnaam zonder extensie (bijv. jura-z10-main)"
    echo "  [categorie]    Optioneel: volautomaten, espressomachines, bonenmolens, accessoires"
    exit 1
fi

IMAGE_URL="$1"
OUTPUT_NAME="$2"
CATEGORY="${3:-uncategorized}"

# Bepaal het domein voor de Referer header
DOMAIN=$(echo "$IMAGE_URL" | sed -E 's|https?://([^/]+).*|\1|')

echo -e "${BLUE}=== Koffiemachine Image Finder ===${NC}"
echo -e "URL:       $IMAGE_URL"
echo -e "Naam:      $OUTPUT_NAME"
echo -e "Categorie: $CATEGORY"
echo -e "Domein:    $DOMAIN"
echo ""

# --- Mappen aanmaken ---
PRODUCT_DIR="$OUTPUT_BASE/products/$CATEGORY"
THUMB_DIR="$OUTPUT_BASE/thumbnails/$CATEGORY"
mkdir -p "$PRODUCT_DIR" "$THUMB_DIR"

# --- Stap 1: Download ---
echo -e "${YELLOW}[1/5] Downloaden...${NC}"
TEMP_FILE="/tmp/koffie-img-$$"

HTTP_CODE=$(curl -L -s -w "%{http_code}" \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36" \
    -H "Accept: image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8" \
    -H "Referer: https://$DOMAIN/" \
    -H "Accept-Language: nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7" \
    -o "$TEMP_FILE" \
    "$IMAGE_URL")

if [ "$HTTP_CODE" != "200" ]; then
    echo -e "${RED}FOUT: HTTP status $HTTP_CODE${NC}"
    echo -e "${YELLOW}Tip: Probeer og:image of een CDN-URL als alternatief${NC}"
    rm -f "$TEMP_FILE"
    exit 1
fi

# --- Stap 2: Validatie ---
echo -e "${YELLOW}[2/5] Valideren...${NC}"

FILE_SIZE=$(stat -f%z "$TEMP_FILE" 2>/dev/null || stat -c%s "$TEMP_FILE" 2>/dev/null)
FILE_TYPE=$(file -b "$TEMP_FILE")

echo -e "  Type:    $FILE_TYPE"
echo -e "  Grootte: $FILE_SIZE bytes"

# Check of het een afbeelding is
if echo "$FILE_TYPE" | grep -qiE "html|text|xml|json"; then
    echo -e "${RED}FOUT: Gedownload bestand is geen afbeelding maar $FILE_TYPE${NC}"
    echo -e "${YELLOW}Mogelijke oorzaken:${NC}"
    echo -e "  - 403/captcha pagina geretourneerd"
    echo -e "  - Redirect naar loginpagina"
    echo -e "  - Bot-detectie actief"
    echo -e "${YELLOW}Tip: Probeer og:image URL of een webshop (Coolblue, MediaMarkt)${NC}"
    rm -f "$TEMP_FILE"
    exit 1
fi

# Check minimale grootte
if [ "$FILE_SIZE" -lt "$MIN_FILE_SIZE" ]; then
    echo -e "${RED}WAARSCHUWING: Bestand is erg klein ($FILE_SIZE bytes)${NC}"
    echo -e "${YELLOW}Dit is mogelijk een placeholder/tracking pixel${NC}"
    echo -e "${YELLOW}Doorgaan? Het resultaat kan een lege of minuscule afbeelding zijn.${NC}"
fi

# --- Stap 3: Conversie (indien nodig) ---
echo -e "${YELLOW}[3/5] Converteren...${NC}"

# Detecteer formaat en converteer naar JPG als basisformaat
if echo "$FILE_TYPE" | grep -qi "webp"; then
    echo -e "  WebP gedetecteerd -> converteren naar JPG"
    convert "$TEMP_FILE" "$TEMP_FILE.jpg" 2>/dev/null || magick "$TEMP_FILE" "$TEMP_FILE.jpg" 2>/dev/null
    mv "$TEMP_FILE.jpg" "$TEMP_FILE"
elif echo "$FILE_TYPE" | grep -qi "avif"; then
    echo -e "  AVIF gedetecteerd -> converteren naar JPG"
    magick "$TEMP_FILE" "$TEMP_FILE.jpg" 2>/dev/null || ffmpeg -y -i "$TEMP_FILE" "$TEMP_FILE.jpg" 2>/dev/null
    mv "$TEMP_FILE.jpg" "$TEMP_FILE"
elif echo "$FILE_TYPE" | grep -qi "svg"; then
    echo -e "  SVG gedetecteerd -> converteren naar JPG"
    convert -background white -density 300 "$TEMP_FILE" "$TEMP_FILE.jpg" 2>/dev/null
    mv "$TEMP_FILE.jpg" "$TEMP_FILE"
elif echo "$FILE_TYPE" | grep -qi "png"; then
    echo -e "  PNG gedetecteerd -> flatten naar witte achtergrond"
    convert "$TEMP_FILE" -background white -flatten "$TEMP_FILE.jpg" 2>/dev/null
    mv "$TEMP_FILE.jpg" "$TEMP_FILE"
else
    echo -e "  ${GREEN}JPG/JPEG — geen conversie nodig${NC}"
fi

# --- Stap 4: Resize & Optimaliseer ---
echo -e "${YELLOW}[4/5] Resize & optimaliseren...${NC}"

# Hoofdafbeelding (800x800, behoud aspect ratio)
MAIN_OUTPUT="$PRODUCT_DIR/${OUTPUT_NAME}.jpg"
convert "$TEMP_FILE" -resize "${MAIN_SIZE}>" -quality $JPG_QUALITY "$MAIN_OUTPUT" 2>/dev/null

# WebP versie
WEBP_OUTPUT="$PRODUCT_DIR/${OUTPUT_NAME}.webp"
convert "$TEMP_FILE" -resize "${MAIN_SIZE}>" -quality $WEBP_QUALITY "$WEBP_OUTPUT" 2>/dev/null

# Thumbnail
THUMB_OUTPUT="$THUMB_DIR/${OUTPUT_NAME}-thumb.jpg"
convert "$TEMP_FILE" -resize "${THUMB_SIZE}>" -quality $THUMB_QUALITY "$THUMB_OUTPUT" 2>/dev/null

# --- Stap 5: Rapport ---
echo -e "${YELLOW}[5/5] Klaar!${NC}"
echo ""
echo -e "${GREEN}=== Resultaat ===${NC}"
echo -e "  Main JPG:  $MAIN_OUTPUT ($(stat -f%z "$MAIN_OUTPUT" 2>/dev/null || stat -c%s "$MAIN_OUTPUT" 2>/dev/null) bytes)"
echo -e "  Main WebP: $WEBP_OUTPUT ($(stat -f%z "$WEBP_OUTPUT" 2>/dev/null || stat -c%s "$WEBP_OUTPUT" 2>/dev/null) bytes)"
echo -e "  Thumbnail: $THUMB_OUTPUT ($(stat -f%z "$THUMB_OUTPUT" 2>/dev/null || stat -c%s "$THUMB_OUTPUT" 2>/dev/null) bytes)"

# Toon afmetingen
echo ""
echo -e "${BLUE}Afmetingen:${NC}"
identify "$MAIN_OUTPUT" 2>/dev/null | awk '{print "  Main:      " $3}'
identify "$THUMB_OUTPUT" 2>/dev/null | awk '{print "  Thumbnail: " $3}'

# HTML snippet
echo ""
echo -e "${BLUE}HTML snippet:${NC}"
cat << EOF
<picture>
  <source srcset="images/products/$CATEGORY/${OUTPUT_NAME}.webp" type="image/webp">
  <img src="images/products/$CATEGORY/${OUTPUT_NAME}.jpg"
       alt="${OUTPUT_NAME} | Koffiemachinewijzer"
       width="800" height="800"
       loading="lazy"
       decoding="async">
</picture>
EOF

# Opruimen
rm -f "$TEMP_FILE"

echo ""
echo -e "${GREEN}Klaar!${NC}"
