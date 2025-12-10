#!/usr/bin/env bash
export TZ="America/Toronto"
set -euo pipefail

# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------
echo ""
echo "================ TV SYNC: $(date '+%Y-%m-%d %H:%M:%S') ================"
echo ""

# ---------------------------------------------------------
# INPUT / PATHS
# ---------------------------------------------------------
SRC="${1:-/mnt/debrid/riven_symlinks/shows}"
DEST="/media/shows"

UPDATE_LAST_FILE=true
FULL=false
FILTER_SHOW=""
FILTER_EPISODE=""

# Parse arguments in a single pass
if [[ -d "${1:-}" ]]; then
    SRC="$1"
    shift
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full) FULL=true; UPDATE_LAST_FILE=false ;;
        --show) FILTER_SHOW="$2"; UPDATE_LAST_FILE=false; shift ;;
        --episode) FILTER_EPISODE="$2"; UPDATE_LAST_FILE=false; shift ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
    shift
done

# ---------------------------------------------------------
# TIMESTAMP CACHE
# ---------------------------------------------------------
CACHE_DIR="/opt/riven-cache"
mkdir -p "$CACHE_DIR"

if [[ "$SRC" == *"/mnt/debrid_1080/"* ]]; then
    LAST_FILE="$CACHE_DIR/tv-1080.last"
    DEFAULT_RES="1080p"
else
    LAST_FILE="$CACHE_DIR/tv-4k.last"
    DEFAULT_RES="2160p"
fi

touch "$LAST_FILE"

if $FULL; then
    PREV_TS=0
else
    PREV_TS=$(<"$LAST_FILE")
fi

[[ "$PREV_TS" =~ ^[0-9]+$ ]] || PREV_TS=0
NOW_TS=$(date +%s)

echo ""
echo "TV SYNC:"
echo " SRC            = $SRC"
echo " PREV_TS        = $PREV_TS"
echo " FULL MODE      = $FULL"
echo " FILTER_SHOW    = '$FILTER_SHOW'"
echo " FILTER_EPISODE = '$FILTER_EPISODE'"
echo ""

# Track whether any actual processing happened
PROCESSED_ANY=false

# ---------------------------------------------------------
# RESOLUTION HELPERS
# ---------------------------------------------------------
filename_detect_resolution(){ local n="$1"; [[ "$n" =~ 2160|4K|UHD ]] && echo "2160p" && return; [[ "$n" =~ 1080 ]] && echo "1080p" && return; echo "UNKNOWN"; }
keyword_infer_resolution(){ local n="$1"; [[ "$n" =~ DV|DoVi|HDR ]] && echo "2160p" && return; [[ "$n" =~ AVC ]] && echo "1080p" && return; echo "UNKNOWN"; }
folder_detect_resolution(){ local n="$1"; [[ "$n" =~ 2160|4K ]] && echo "2160p" && return; [[ "$n" =~ 1080 ]] && echo "1080p" && return; echo "UNKNOWN"; }

probe_resolution() {
    local FILE="$1"
    local OUT
    OUT=$(timeout 5s ffprobe -v error -select_streams v:0 \
        -show_entries stream=width -of csv=p=0 "$FILE" 2>/dev/null) || OUT=""
    [[ -z "$OUT" ]] && echo "UNKNOWN" && return
    (( OUT >= 3800 )) && echo "2160p" && return
    (( OUT >= 1900 )) && echo "1080p" && return
    echo "720p"
}

# ---------------------------------------------------------
# PROCESS SYMLINK
# ---------------------------------------------------------
process_symlink() {
    local LINK="$1"
    local BASENAME SHOW SEASON SHOW_DIR SEASON_DIR

    BASENAME=$(basename "$LINK")
    SHOW_DIR=$(dirname "$LINK")
    SEASON_DIR=$(dirname "$SHOW_DIR")
    SHOW=$(basename "$SEASON_DIR")
    SEASON=$(basename "$SHOW_DIR")

    # Episode extraction for optional filtering
    local EP=""
    if [[ "$BASENAME" =~ ([Ss][0-9]{2}[Ee][0-9]{2}) ]]; then
        EP="${BASH_REMATCH[1]}"
    fi

    if [[ -n "$FILTER_EPISODE" && "$EP" != "$FILTER_EPISODE" ]]; then
        return
    fi

    # Real file resolution detection
    local TARGET
    TARGET=$(readlink -f "$LINK")
    if [[ ! -f "$TARGET" ]]; then
        echo "Broken symlink: $LINK"
        return
    fi

    local RES REAL_PARENT
    RES=$(filename_detect_resolution "$TARGET")
    [[ "$RES" == "UNKNOWN" ]] && RES=$(keyword_infer_resolution "$TARGET")
    REAL_PARENT=$(basename "$(dirname "$TARGET")")
    [[ "$RES" == "UNKNOWN" ]] && RES=$(folder_detect_resolution "$REAL_PARENT")
    [[ "$RES" == "UNKNOWN" ]] && RES=$(probe_resolution "$TARGET")
    [[ "$RES" == "UNKNOWN" ]] && RES="$DEFAULT_RES"

    # Rename symlink if necessary
    if [[ "$BASENAME" != *"$RES"* ]]; then
        local EXT NAME NEW_NAME
        EXT="${BASENAME##*.}"
        NAME="${BASENAME%.*}"
        NEW_NAME="${NAME} - ${RES}.${EXT}"
        mv "$LINK" "$(dirname "$LINK")/$NEW_NAME"
        LINK="$(dirname "$LINK")/$NEW_NAME"
        BASENAME="$NEW_NAME"
        echo " RENAMED: $BASENAME"
        PROCESSED_ANY=true
    fi

    # Create Jellyfin link
    mkdir -p "$DEST/$SHOW/$SEASON"
    local DEST_PATH="$DEST/$SHOW/$SEASON/$BASENAME"

    if [[ -L "$DEST_PATH" ]]; then
        echo " Already linked: $DEST_PATH"
        return
    fi

    local TMP="$DEST_PATH.$$"
    ln -s "$TARGET" "$TMP"
    mv -T "$TMP" "$DEST_PATH"
    echo " Linked: $DEST_PATH"
    PROCESSED_ANY=true
}

# ================================================================
#                   FAST SYMLINK-MTIME MAIN LOOP (PARENTSHELL)
# ================================================================
# use null-separated records, keep while in parent shell via process substitution

while IFS= read -r -d $'\0' LINE; do
    TS="${LINE%%$'\t'*}"
    LINK="${LINE#*$'\t'}"

    # ----------------------------------------------------
    # TARGET SHOW FILTERING (skip everything else early!)
    # ----------------------------------------------------
    if [[ -n "$FILTER_SHOW" ]]; then
        SHOW_NAME=$(basename "$(dirname "$(dirname "$LINK")")")
        if [[ "$SHOW_NAME" != "$FILTER_SHOW" ]]; then
            continue
        fi
    fi

    # --------------------------------------------------------
    # EARLY STOP: Only in non-filter, non-full mode
    # --------------------------------------------------------
    if ! $FULL && [[ -z "$FILTER_SHOW" && -z "$FILTER_EPISODE" ]]; then
        if (( TS <= PREV_TS )); then
            echo "Stopping early: symlink <= last-run"
            break
        fi
    fi

    echo "NEW: $LINK"
    process_symlink "$LINK"
done < <(
    perl -MFile::Find -MFile::stat -e '
      my $src = shift;
      find(sub {
        return unless -l $_;
        my $p = $File::Find::name;
        my $s = File::stat::lstat($p);
        printf "%d\t%s\0", $s->mtime, $p;
      }, $src);
    ' "$SRC" | sort -z -nr -k1,1 2>/dev/null || true
)



# ---------------------------------------------------------
# TIMESTAMP UPDATE (only if not forced mode and work happened)
# ---------------------------------------------------------
if [[ "$UPDATE_LAST_FILE" == true && "$PROCESSED_ANY" == true ]]; then
    echo "$NOW_TS" > "$LAST_FILE"
    HUMAN_TS=$(date -d @"$NOW_TS" +"%Y-%m-%d %H:%M:%S")
    echo "Updated timestamp: $HUMAN_TS ($NOW_TS)"
elif [[ "$UPDATE_LAST_FILE" == true && "$PROCESSED_ANY" != true ]]; then
    echo "No changes detected; timestamp not updated."
else
    echo "Skipped timestamp update (targeted or full refresh)."
fi

echo "TV SYNC COMPLETE"
