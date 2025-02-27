#!/bin/bash
#
# brl.sh (Master Script for BR-Lite)
#
# This script, when run from the FIDIM directory, performs the following:
#   1. Ensures all required scripts have executable permissions.
#   2. Optionally runs first-time installation tasks.
#   3. Executes:
#         a. process_source.sh
#         b. co_traveler_merge.sh
#         c. co_traveler_analysis.py
#   4. Prompts the user for maintenance tasks:
#         - Archive Data: moves files older than a user-specified cutoff date.
#         - Ragnarok: (if confirmed) deletes all files and directories in BR-Lite except FIDIM.
#
# Note: The cleaning step (co_traveler_clean.sh) has been removed.
#

# Determine the BR-Lite base directory (parent of FIDIM)
BASE_DIR="$(realpath "$(dirname "$0")/../")"
echo "BR-Lite base directory: $BASE_DIR"

# Recursively update permissions for all .sh and .py files in the BR-Lite directory.
echo "Updating execute permissions for all .sh and .py files in the BR-Lite directory..."
find "$BASE_DIR" -type f \( -iname "*.sh" -o -iname "*.py" \) -exec chmod +x {} \;
echo "All script permissions updated."

# Prompt to run first time installation tasks
read -p "Would you like to run first time installation tasks? (y/n): " install_choice
if [[ "$install_choice" =~ ^[Yy] ]]; then
    echo "Starting BR-Lite Installer..."
    ./installer.sh || { echo "Installer failed. Exiting."; exit 1; }
else
    echo "Installation tasks skipped."
fi

# Check that required scripts exist in the current (FIDIM) directory.
SCRIPTS=("installer.sh" "process_source.sh" "co_traveler_merge.sh" "co_traveler_analysis.py")
echo "Checking script permissions..."
for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        chmod +x "$script"
        echo "Ensured $script is executable."
    else
        echo "Error: $script not found in the current directory. Confirm you have downloaded all BR-Lite files. Exiting."
        exit 1
    fi
done
echo "All required scripts are present and executable."

# Ensure Whitelist.csv exists in the BR-Lite base directory
WHITELIST_FILE="$BASE_DIR/Whitelist.csv"

if [ ! -f "$WHITELIST_FILE" ]; then
    echo "Creating Whitelist.csv with default headers..."
    echo "Device Name,Device Type,Wifi MAC Address,Bluetooth MAC Address,Randomized Wifi,Randomized BT" > "$WHITELIST_FILE"
else
    echo "Whitelist.csv already exists. No changes made."
fi

# Prompt for data analysis
read -p "Have you uploaded your data for analysis? Ensure your data is in the appropriate directory in the Input_Data folder. (y/n): " analyze_choice
if [[ ! "$analyze_choice" =~ ^[Yy] ]]; then
    echo "Data analysis skipped. Exiting master script."
    exit 0
fi

echo "Extracting data from Kimset and Airodump files"
./process_source.sh || { echo "Source processing failed. Exiting."; exit 1; }

echo "Merging processed data for Co Traveler Analysis..."
./co_traveler_merge.sh || { echo "Merging failed. Exiting."; exit 1; }

echo "Analyzing Co Traveler data and generating maps..."
./co_traveler_analysis.py || { echo "Analysis failed. Exiting."; exit 1; }

echo "Aggregating static signals..."
./static_aggregate.py || { echo "Static signals aggregation failed. Exiting."; exit 1; }

echo "Generating static signals map..."
./static_signals_map.py || { echo "Static signals map generation failed. Exiting."; exit 1; }

echo "Running Flagged Signal Analysis"
./flagged_signals_analysis.py || { echo "Flagged Signal Analysis failed. Exiting."; exit 1; }

echo "Bulk Analysis complete, considering Targeted Analytical Options"
./targeted_analytics.py || { echo "Targeted Analysis failed. Exiting."; exit 1; }

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
