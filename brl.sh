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

# load vars from config
for key in $(yq e 'keys | .[]' config.yaml); do
  export "$key=$(yq e ".$key" config.yaml)"
done

# Prompt for data analysis
read -p "Have you uploaded your data for analysis? Ensure your data is in the appropriate directory in the Input_Data folder. (y/n): " analyze_choice
if [[ ! "$analyze_choice" =~ ^[Yy] ]]; then
    echo "Data analysis skipped. Exiting master script."
    exit 0
fi

echo "Extracting data from Kimset and Airodump files"
./src/process_source.sh || { echo "Source processing failed. Exiting."; exit 1; }

echo "Merging processed data for co-traveler Analysis..."
./src/co_traveler_merge.sh || { echo "Merging failed. Exiting."; exit 1; }

echo "Analyzing co-traveler data and generating maps..."
./src/co_traveler_analysis.py || { echo "Analysis failed. Exiting."; exit 1; }

echo "Aggregating static signals..."
./src/static_aggregate.py || { echo "Static signals aggregation failed. Exiting."; exit 1; }

echo "Generating static signals map..."
./src/static_signals_map.py || { echo "Static signals map generation failed. Exiting."; exit 1; }

echo "Running Flagged Signal Analysis"
./src/flagged_signals_analysis.py || { echo "Flagged Signal Analysis failed. Exiting."; exit 1; }

echo "Bulk Analysis complete, considering Targeted Analytical Options"
./src/targeted_analytics.py || { echo "Targeted Analysis failed. Exiting."; exit 1; }

echo "BR-Lite main tasks complete."

# -----------------------------
# Maintenance Tasks
# -----------------------------
read -p "Would you like to complete maintenance tasks? (y/n): " maint_choice
if [[ "$maint_choice" =~ ^[Nn] ]]; then
    echo "Maintenance tasks skipped. Stay safe out there - DET 2324."
    exit 0
fi

# Archive Data Task
read -p "Would you like to archive data? (y/n): " archive_choice
if [[ "$archive_choice" =~ ^[Yy] ]]; then
    read -p "Enter cutoff date (DD-MM-YYYY) to archive all files older than or equal to that date: " cutoff_date
    echo "Archiving files older than or equal to $cutoff_date..."
    ARCHIVE_DIR="$BASE_DIR/Archive"
    mkdir -p "$ARCHIVE_DIR"
    DIRS_TO_ARCHIVE=("$BASE_DIR/Input_Data" "$BASE_DIR/Processing" "$BASE_DIR/Outputs")
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
read -p "Do you want to initiate Ragnarok to delete all analyzed data? (y/n): " ragnarok_choice
if [[ "$ragnarok_choice" =~ ^[Yy] ]]; then
    read -p "WARNING: This action will delete ALL files and directories outside of Input_Data. You will have to re-run installer and analysis processes? (y/n): " confirm_ragnarok
    if [[ "$confirm_ragnarok" =~ ^[Yy] ]]; then
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

echo "Maintenance tasks complete. Stay safe out there - DET 2324"
exit 0
