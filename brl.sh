#!/bin/bash
#
# brl.sh (Master Script for BR-Lite)
#
# This script, when run from the FIDIM directory, performs the following:
#   1. Ensures all required scripts have executable permissions.
#   2. Optionally runs first-time installation tasks.
#   3. Executes the following sequentially:
#         a. process_source.sh
#         b. co_traveler_merge.sh
#         c. co_traveler_analysis.py
#         d. static_aggregate.py
#         e. static_signals_map.py
#         f. flagged_signals_analysis.py
#         g. targeted_analytics.py
#   4. Prompts the user for maintenance tasks:
#         - Archive Data: moves files older than a user-specified cutoff date.
#         - Ragnarok: (if confirmed) deletes all files and directories in BR-Lite except FIDIM.

# strict shell settings
set -euo pipefail
IFS=$'\n\t'

source $(dirname "$0")/src/utils.sh

# load vars from config
for key in $(yq e 'keys | .[]' config.yaml); do
  export "$key=$(yq e ".$key" config.yaml)"
done

# Prompt for data analysis
if prompt_confirm "Perform analysis? Required datasets must be in the appropriate data subdirectories." "Y"; then

    echo "Extracting data from Kimset and Airodump files"
    ./src/process_source.sh || { echo "Source processing failed. Exiting."; exit 1; }

    echo "Merging processed data for co-traveler Analysis..."
    ./src/co_traveler_merge.sh || { echo "Merging failed. Exiting."; exit 1; }

    # echo "Analyzing co-traveler data and generating maps..."
    # ./src/co_traveler_analysis.py || { echo "Analysis failed. Exiting."; exit 1; }

    # echo "Aggregating static signals..."
    # ./src/static_aggregate.py || { echo "Static signals aggregation failed. Exiting."; exit 1; }

    # echo "Generating static signals map..."
    # ./src/static_signals_map.py || { echo "Static signals map generation failed. Exiting."; exit 1; }

    # echo "Running Flagged Signal Analysis"
    # ./src/flagged_signals_analysis.py || { echo "Flagged Signal Analysis failed. Exiting."; exit 1; }

    # echo "Bulk Analysis complete, considering Targeted Analytical Options"
    # ./src/targeted_analytics.py || { echo "Targeted Analysis failed. Exiting."; exit 1; }

    echo "BR-Lite main tasks complete."
else
    echo "Data analysis skipped."
fi

# -----------------------------
# Maintenance Tasks
# -----------------------------
if prompt_confirm "Perform maintenance tasks?"; then
    # Archive Data Task
    if prompt_confirm "Archive data?"; then
        read -p "Enter cutoff date (DD-MM-YYYY) to archive all files older than or equal to that date: " cutoff_date
        echo "Archiving files older than or equal to $cutoff_date..."
        # INPUT_ARCHIVE_DIR is defined in config.yaml
        mkdir -p "$ARCHIVE_DIR"
        DIRS_TO_ARCHIVE=("$INPUT_DIR" "$PROCESSED_DIR" "$OUTPUT_DIR")
        for dir in "${DIRS_TO_ARCHIVE[@]}"; do
            if [ -d "$dir" ]; then
                echo "Archiving from $dir..."
                find "$dir" -type f ! -newermt "$cutoff_date" -exec mv {} "$ARCHIVE_DIR" \;
            fi
        done
        echo "Data archiving complete."
    else
        echo "Data archiving skipped."
    fi

    # Ragnarok Task
    if prompt_confirm "Initiate Ragnarok? This will delete all analyzed data."; then
        echo "WARNING: This operation is irreversible."
        if prompt_confirm "Confirm final delete?"; then
            echo "Initiating Ragnarok..."

            for item in "$BASE_DIR"/*; do
                base_item=$(basename "$item")
                if [ "$base_item" != "FIDIM" ] && [ "$base_item" != "Input_Data" ]; then
                    echo "Deleting $item..."
                    sudo rm -rf "$item"
                fi
            done
            echo "Ragnarok complete. All files except FIDIM have been deleted."
        else
            echo "Ragnarok canceled."
        fi
    else
        echo "Ragnarok skipped."
    fi
    echo "Maintenance tasks complete."
else
    echo "Maintenance tasks skipped."
fi

echo "Stay safe out there - DET 2324."
