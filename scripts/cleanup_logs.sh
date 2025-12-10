#!/usr/bin/env bash

# ---------------------------------------------------------
# LOG CLEANUP SCRIPT
# ---------------------------------------------------------
# Keeps only the last N days of each log file based on timestamp headers
# Usage: cleanup_logs.sh [--keep-days N] [--clear-all] [--dry-run]

KEEP_DAYS=3
CLEAR_ALL=false
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep-days)
            KEEP_DAYS="$2"
            shift 2
            ;;
        --clear-all)
            CLEAR_ALL=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# Log files to clean
BASE="/opt/docker/logs"
LOG_FILES=(
    "$BASE/tv_1080.log"
    "$BASE/tv_4k.log"
    "$BASE/movie_1080.log"
    "$BASE/movie_4k.log"
)

echo "Log Cleanup Script"
echo "=================="
if $CLEAR_ALL; then
    echo "Mode: CLEAR ALL LOGS"
else
    echo "Keep Days: $KEEP_DAYS"
fi
echo "Dry Run: $DRY_RUN"
echo ""

cleanup_log_file() {
    local LOG_FILE="$1"
    local KEEP_DAYS="$2"
    local CLEAR="$3"
    local DRY="$4"

    if [[ ! -f "$LOG_FILE" ]]; then
        echo "⚠️  Skip (not found): $LOG_FILE"
        return
    fi

    if $CLEAR; then
        local ORIGINAL_SIZE=$(wc -c < "$LOG_FILE")
        local SIZE_REDUCTION=$(numfmt --to=iec "$ORIGINAL_SIZE" 2>/dev/null || echo "$ORIGINAL_SIZE bytes")

        if $DRY; then
            echo "→ Would clear entire log: $LOG_FILE"
            echo "  Size to remove: $SIZE_REDUCTION"
        else
            > "$LOG_FILE"
            echo "✓ Cleared: $LOG_FILE"
            echo "  Removed: $SIZE_REDUCTION"
        fi
        return
    fi

    # Calculate cutoff date
    local CUTOFF_DATE=$(date -d "$KEEP_DAYS days ago" +"%Y-%m-%d")
    local CUTOFF_TS=$(date -d "$CUTOFF_DATE" +%s)

    # Find the first line that has a timestamp newer than cutoff
    local START_LINE=1
    while IFS= read -r line; do
        if [[ "$line" =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2}) ]]; then
            local TIMESTAMP="${BASH_REMATCH[1]}"
            local LINE_TS=$(date -d "$TIMESTAMP" +%s 2>/dev/null || echo 0)
            if (( LINE_TS >= CUTOFF_TS )); then
                break
            fi
            START_LINE=$((START_LINE + 1))
        else
            START_LINE=$((START_LINE + 1))
        fi
    done < "$LOG_FILE"

    if (( START_LINE == 1 )); then
        echo "✓ Skip (all logs within $KEEP_DAYS days): $LOG_FILE"
        return
    fi

    local ORIGINAL_SIZE=$(wc -c < "$LOG_FILE")
    local NEW_SIZE=$(tail -n +$START_LINE "$LOG_FILE" 2>/dev/null | wc -c)
    local SIZE_REDUCTION=$(numfmt --to=iec $((ORIGINAL_SIZE - NEW_SIZE)) 2>/dev/null || echo "$((ORIGINAL_SIZE - NEW_SIZE)) bytes")

    if $DRY; then
        echo "→ Would remove (keep $KEEP_DAYS days): $LOG_FILE"
        echo "  Cutoff date: $CUTOFF_DATE"
        echo "  Lines to remove: $((START_LINE - 1))"
        echo "  Size reduction: $SIZE_REDUCTION"
    else
        if (( START_LINE > 1 )); then
            tail -n +$START_LINE "$LOG_FILE" > "$LOG_FILE.tmp"
            mv "$LOG_FILE.tmp" "$LOG_FILE"
            echo "✓ Cleaned (keep $KEEP_DAYS days): $LOG_FILE"
            echo "  Removed $((START_LINE - 1)) lines ($SIZE_REDUCTION)"
        fi
    fi
}

# Process each log file
for LOG_FILE in "${LOG_FILES[@]}"; do
    cleanup_log_file "$LOG_FILE" "$KEEP_DAYS" "$CLEAR_ALL" "$DRY_RUN"
done

echo ""
if $DRY_RUN; then
    echo "Dry run complete. Re-run without --dry-run to apply changes."
else
    echo "Log cleanup complete."
fi
