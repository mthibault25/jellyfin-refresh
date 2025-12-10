#!/usr/bin/env bash
set -euo pipefail

# ========== COLORS ==========
RED="\e[31m"
GREEN="\e[32m"
YELLOW="\e[33m"
BLUE="\e[34m"
CYAN="\e[36m"
BOLD="\e[1m"
RESET="\e[0m"
# ============================

# ----------------------------------------------------------
# CONFIG PATHS
# ----------------------------------------------------------

BASENAME="/mnt/debrid/riven_symlinks"
BASENAME_1080="/mnt/debrid_1080/riven_symlinks"

MOVIES_SCRIPT="/opt/docker/scripts/sync_movies_folders.sh"
SHOWS_SCRIPT="/opt/docker/scripts/sync_tv_folders.sh"

sudo chown -R 1000 /media >/dev/null 2>&1 || true


# ----------------------------------------------------------
# MENU
# ----------------------------------------------------------

menu() {
    echo -e "
=========== RIVEN MEDIA REFRESH MENU ===========

1.  Refresh ALL Media (Movies + Shows) FULL
2.  Refresh MOVIES Only FULL
3.  Refresh SHOWS Only FULL
4.  Refresh ONE Show (fuzzy search)
5.  Refresh ONE Movie (fuzzy search)
6.  Copy Shows ONLY (new items only)
7.  Copy Movies ONLY (new items only)
8.  List all Shows
9.  List all Movies
10. Show FULL details of ONE Show
0.  Exit

================================================
"
}

# ----------------------------------------------------------
# LISTING — PRETTY FORMAT
# ----------------------------------------------------------

pretty_list() {
    local DIR="$1"

    echo ""
    echo "----------------------------------------"
    echo "   Listing: $(basename "$DIR")"
    echo "----------------------------------------"

    if [[ ! -d "$DIR" ]]; then
        echo "❌ Directory not found: $DIR"
        return
    fi

    mapfile -t ITEMS < <(find "$DIR" -maxdepth 1 -mindepth 1 -type d -printf "%f\n" | sort)

    if (( ${#ITEMS[@]} == 0 )); then
        echo "No entries found."
        return
    fi

    local index=1
    for item in "${ITEMS[@]}"; do
        printf "%3d) %s\n" "$index" "$item"
        (( index++ ))
    done
    echo ""
}

# ----------------------------------------------------------
# FUZZY SEARCH
# ----------------------------------------------------------

find_match() {
    local SEARCH="$1"
    local BASE="$2"

    mapfile -t MATCHES < <(
        find "$BASE" -maxdepth 1 -mindepth 1 -type d \
            -iname "*$SEARCH*" -printf "%f\n" | sort
    )

    if (( ${#MATCHES[@]} == 0 )); then
        echo "❌ No matches found for: $SEARCH"
        return 1
    fi

    # Single match
    if (( ${#MATCHES[@]} == 1 )); then
        SELECTED="${MATCHES[0]}"
        return 0
    fi

    # Multiple matches
    echo "Multiple matches found:"
    local i=1
    for m in "${MATCHES[@]}"; do
        printf "  %2d) %s\n" "$i" "$m"
        (( i++ ))
    done

    read -p "Select number: " NUM
    if [[ "$NUM" =~ ^[0-9]+$ ]] && (( NUM>=1 && NUM<=${#MATCHES[@]} )); then
        SELECTED="${MATCHES[$((NUM-1))]}"
        return 0
    fi

    echo "❌ Invalid selection."
    return 1
}

show_full_details() {
    local SHOW="$1"
    local BASE="/media/shows/$SHOW"

    if [[ ! -d "$BASE" ]]; then
        echo "❌ Show folder not found: $BASE"
        return
    fi

    echo ""
    echo "====================================================="
    echo "   FULL DETAILS FOR: $SHOW"
    echo "====================================================="

    # Get seasons safely
    mapfile -d '' -t SEASONS < <(
        find "$BASE" -mindepth 1 -maxdepth 1 -type d -print0 |
        sort -z
    )

    if (( ${#SEASONS[@]} == 0 )); then
        echo "(no seasons found)"
        return
    fi

    for SEASON_PATH in "${SEASONS[@]}"; do
        SEASON=$(basename "$SEASON_PATH")

        echo ""
        echo "📂 $SEASON"
        echo "-----------------------------------------------------"

        # Get episode files safely
        mapfile -d '' -t EPISODES < <(
            find "$SEASON_PATH" -maxdepth 1 -type l \
                \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" \) -print0 |
            sort -z
        )

        if (( ${#EPISODES[@]} == 0 )); then
            echo "   (no episodes)"
            continue
        fi

        for EFILE in "${EPISODES[@]}"; do
            E=$(basename "$EFILE")

            # Extract SxxEyy
            if [[ "$E" =~ ([Ss][0-9]{2}[Ee][0-9]{2}) ]]; then
                EP="${BASH_REMATCH[1]}"
            else
                EP="--"
            fi

            # Auto-detect resolution from filename
            if [[ "$E" =~ 2160p|2160|UHD|4K ]]; then
                COLOR="$GREEN"
            elif [[ "$E" =~ 1080p|1080 ]]; then
                COLOR="$BLUE"
            elif [[ "$E" =~ 720p|720 ]]; then
                COLOR="$YELLOW"
            else
                COLOR="$RESET"
            fi

            printf "   ${BOLD}%-8s${RESET}  ${COLOR}%s${RESET}\n" "$EP" "$E"
        done

    done

    echo ""
}

# ----------------------------------------------------------
# MAIN LOOP
# ----------------------------------------------------------

while true; do
    menu
    read -p "Enter option: " option

    case "$option" in

# FULL MEDIA (ALL)
    1)
        echo "🔥 FULL refresh: Movies + Shows"
        "$MOVIES_SCRIPT" "$BASENAME/movies" --full
        "$MOVIES_SCRIPT" "$BASENAME_1080/movies" --full
        "$SHOWS_SCRIPT" "$BASENAME/shows" --full
        "$SHOWS_SCRIPT" "$BASENAME_1080/shows" --full
        echo "✅ ALL MEDIA fully refreshed."
        ;;

# FULL MOVIES
    2)
        echo "🎬 FULL movie refresh"
        "$MOVIES_SCRIPT" "$BASENAME/movies" --full
        "$MOVIES_SCRIPT" "$BASENAME_1080/movies" --full
        echo "✅ Movies refreshed."
        ;;

# FULL SHOWS
    3)
        echo "📺 FULL show refresh"
        "$SHOWS_SCRIPT" "$BASENAME/shows" --full
        "$SHOWS_SCRIPT" "$BASENAME_1080/shows" --full
        echo "✅ Shows refreshed."
        ;;

# ONE SHOW REFRESH
    4)
        read -p "Enter part of the show name: " show_name

        if find_match "$show_name" "/media/shows"; then
            read -p "Refresh show '$SELECTED'? (y/n): " yn
            [[ "$yn" != "y" ]] && continue

            "$SHOWS_SCRIPT" "$BASENAME/shows" --show "$SELECTED"
            "$SHOWS_SCRIPT" "$BASENAME_1080/shows" --show "$SELECTED"

            echo "✅ Show refreshed: $SELECTED"
        fi
        ;;

# ONE MOVIE REFRESH
    5)
        read -p "Enter part of the movie name: " movie_name

        if find_match "$movie_name" "/media/movies"; then
            read -p "Refresh movie '$SELECTED'? (y/n): " yn
            [[ "$yn" != "y" ]] && continue

            "$MOVIES_SCRIPT" "$BASENAME/movies" --movie "$SELECTED"
            "$MOVIES_SCRIPT" "$BASENAME_1080/movies" --movie "$SELECTED"

            echo "✅ Movie refreshed: $SELECTED"
        fi
        ;;

# COPY ONLY — SHOWS
    6)
        echo "📺 Copying new SHOWS only..."
        "$SHOWS_SCRIPT" "$BASENAME/shows"
        "$SHOWS_SCRIPT" "$BASENAME_1080/shows"
        echo "✅ Shows copied."
        ;;

# COPY ONLY — MOVIES
    7)
        echo "🎬 Copying new MOVIES only..."
        "$MOVIES_SCRIPT" "$BASENAME/movies"
        "$MOVIES_SCRIPT" "$BASENAME_1080/movies"
        echo "✅ Movies copied."
        ;;

# LIST SHOWS
    8)
        pretty_list "/media/shows"
        ;;

# LIST MOVIES
    9)
        pretty_list "/media/movies"
        ;;

# SHOW FULL DETAILS OF ONE SHOW
    10)
        read -p "Enter part of the show name: " show_name

        if find_match "$show_name" "/media/shows"; then
            echo ""
            echo "Selected show: $SELECTED"
            echo ""

            show_full_details "$SELECTED"
        fi
        ;;

# EXIT
    0)
        echo "Goodbye!"
        exit 0
        ;;

# BAD INPUT
    *)
        echo "❌ Invalid option."
        ;;
    esac
done
