#!/bin/bash
#
# master.sh
#
# Master Script for BR-Lite
#
# This script, when run from the FIDIM directory, performs the following:
#   1. Ensures all required scripts have executable permissions.
#   2. Executes the following scripts in order:
#         a. installer.sh
#         b. process_source.sh
#         c. co_traveler_merge.sh
#         d. co_traveler_clean.sh
#         e. co_traveler_analysis.py
#   3. Prompts the user for maintenance tasks:
#         a. Archive Data – moves files older than a user-specified cutoff date from
#            Input_Data, Processing, and Outputs into an Archive directory.
#         b. Ragnarok – (if confirmed) deletes all files and directories in BR-Lite except
#            the FIDIM directory.
#
# Ensure this script is run from the FIDIM directory.
#

# List of required scripts (assumed to be in the current directory)
SCRIPTS=("installer.sh" "process_source.sh" "co_traveler_merge.sh" "co_traveler_clean.sh" "co_traveler_analysis.py")

echo "Checking script permissions..."

# Loop over each script to ensure it is executable
for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        chmod +x "$script"
        echo "Ensured $script is executable."
    else
        echo "Error: $script not found in the current directory. Exiting."
        exit 1
    fi
done

echo "All required scripts are present and executable."

# Execute the scripts in order

echo "Starting BR-Lite Installer..."
./installer.sh || { echo "Installer failed. Exiting."; exit 1; }

echo "Processing source data..."
./process_source.sh || { echo "Source processing failed. Exiting."; exit 1; }

echo "Merging processed data for Co Traveler Analysis..."
./co_traveler_merge.sh || { echo "Merging failed. Exiting."; exit 1; }

echo "Cleaning merged data..."
./co_traveler_clean.sh || { echo "Cleaning failed. Exiting."; exit 1; }

echo "Analyzing Co Traveler data and generating maps..."
./co_traveler_analysis.py || { echo "Analysis failed. Exiting."; exit 1; }

echo "BR-Lite main tasks complete."

# -----------------------------
# Maintenance Tasks
# -----------------------------
read -p "Would you like to complete maintenance tasks? (y/n): " maint_choice
if [[ "$maint_choice" =~ ^[Nn] ]]; then
    echo "Maintenance tasks skipped. Exiting master script."
    exit 0
fi

# Set the BR-Lite base directory (parent of FIDIM)
BASE_DIR="$(dirname "$(dirname "$0")")"

# ---- Archive Data Task ----
read -p "Would you like to archive data? (y/n): " archive_choice
if [[ "$archive_choice" =~ ^[Yy] ]]; then
    read -p "Enter cutoff date (DD-MM-YYYY) to archive all files older than or equal to that date: " cutoff_date
    echo "Archiving files older than or equal to $cutoff_date..."

    # Create Archive directory in the BR-Lite base directory if not exists
    ARCHIVE_DIR="$BASE_DIR/Archive"
    mkdir -p "$ARCHIVE_DIR"

    # Define directories to archive from
    DIRS_TO_ARCHIVE=("$BASE_DIR/Input_Data" "$BASE_DIR/Processing" "$BASE_DIR/Outputs")

    for dir in "${DIRS_TO_ARCHIVE[@]}"; do
        if [ -d "$dir" ]; then
            echo "Archiving from $dir..."
            # Find and move files (using modification time) older than or equal to cutoff_date.
            # This uses GNU find's -newermt. Files NOT newer than cutoff_date will be moved.
            find "$dir" -type f ! -newermt "$cutoff_date" -exec mv {} "$ARCHIVE_DIR" \;
        fi
    done

    echo "Data archiving complete."
else
    echo "Data archiving skipped."
fi

# ---- Ragnarok Task ----
read -p "Do you want to initiate Ragnarok and delete all files (except the FIDIM directory)? (y/n): " ragnarok_choice
if [[ "$ragnarok_choice" =~ ^[Yy] ]]; then
    read -p "WARNING: This action will delete ALL files and directories in BR-Lite except the FIDIM directory. Are you absolutely sure? (y/n): " confirm_ragnarok
    if [[ "$confirm_ragnarok" =~ ^[Yy] ]]; then
        echo "Initiating Ragnarok..."
        # Loop through all items in the BR-Lite base directory.
        for item in "$BASE_DIR"/*; do
            base_item=$(basename "$item")
            # Do not delete the FIDIM directory.
            if [ "$base_item" != "FIDIM" ]; then
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

echo "Maintenance tasks complete. Exiting master script."
exit 0
