#!/bin/bash
#
# co_traveler_merge.sh
#
# Part of ETL for co-traveler analysis.
#
# This script iterates over the files in the input/ subfolders and concatenates individual:
#   - *_wigle.csv files
#   - Airodump logs
#   - JSON files
# 
# The user can specify a desired date range (format: DD-MM-YYYY).
#
# The merged output is saved to the processed/ and outputs/ folders.

# load vars from config
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
CONFIG_PATH="$SCRIPT_DIR/../config.yaml"
for key in $(yq e 'keys | .[]' $CONFIG_PATH); do
    export "$key=$(yq e ".$key" $CONFIG_PATH)"
done

source $(dirname "$0")/utils.sh

# Explain the processing for the user
echo "***Preparing to merge data from available sensors. Merging will NOT mix sensor data from different sources"
echo "***(i.e. Kismet Wigle Outputs, Kismet JSON outputs, Kismet pcap outputs, and Airodump log files will remain siloed within their format)"
echo "***Better Rover -Lite will use these merged files as databases for downstream analytical processes."
echo "***BR-L can constrain this process to a user-specified date range."
echo "***This is useful if you'd like to constrain future processes to a specific range as opposed to using aggregate data."
echo "***You can re-run BR-Lite to create multiple time-frames for analysis if you don't want to specify it now."
# Prompt for date range
if prompt_confirm "Would you like to specify a date range?" "N"; then
    read -p "Enter start date (DD-MM-YYYY): " start_input
    read -p "Enter end date (DD-MM-YYYY): " end_input
    start_date=$(echo "$start_input" | awk -F- '{printf "%s-%s-%s", $3, $2, $1}')
    end_date=$(echo "$end_input" | awk -F- '{printf "%s-%s-%s", $3, $2, $1}')
    RANGE_LABEL="${start_input}--${end_input}"
else
    TODAY_LABEL=$(date +'%d-%m-%Y')
    RANGE_LABEL="$TODAY_LABEL"
fi

# concatenate individual WiGLE CSV files
OUTPUT_WIGLE_FILE="$PROCESSED_MERGES_DIR/WiGLE_${RANGE_LABEL}.csv"
echo "Merging WiGLE CSV files..."

# Get the first wigle file
first_file=$(find "$INPUT_KISMET_DIR" -type f -name "*_wigle.csv" | head -n 1)
if [ -z "$first_file" ]; then
    echo "No WiGLE CSV files found."
    # don't exit if none found
else
    # Extract the proper header (second line, since the first is the bad row) and append "Source File"
    proper_header=$(sed -n '2p' "$first_file")
    echo "${proper_header},Source File" > "$OUTPUT_WIGLE_FILE"

    # Append data from each wigle file, skipping the first two rows (bad row and header row)
    find "$INPUT_KISMET_DIR" -type f -name "*_wigle.csv" | while read file; do
        tail -n +3 "$file" | awk -v src="$file" 'BEGIN {OFS=","} {print $0, src}'
    done >> "$OUTPUT_WIGLE_FILE"

    echo "WiGLE CSV files merged into $OUTPUT_WIGLE_FILE"
fi

# Merge Airodump logs with removal of "Latitude Error" and "Longitude Error"
# RANGE_LABEL is assumed to be set earlier in the script

# Get header from the first file and remove carriage returns
first_file=$(find "$INPUT_AIRODUMP_DIR" -type f -name "*.log.csv" | head -n 1)
if [ -z "$first_file" ]; then
    echo "No airodump files found."
else
    header_line=$(head -n 1 "$first_file" | tr -d '\r')

    # Split the header into an array and determine which columns to keep
    IFS=',' read -r -a header_fields <<< "$header_line"
    keep_indices=()
    new_header=()
    for i in "${!header_fields[@]}"; do
        field="${header_fields[$i]}"
        # Omit columns named exactly "Latitude Error" or "Longitude Error"
        if [[ "$field" == "Latitude Error" || "$field" == "Longitude Error" ]]; then
            continue
        else
            # Save the 1-based index for awk and build the new header
            keep_indices+=("$((i+1))")
            new_header+=("$field")
        fi
    done

    # Write the new header with an extra "Source File" column
    new_header_line=$(IFS=, ; echo "${new_header[*]}")
    OUTPUT_AIRODUMP_FILE="$PROCESSED_MERGES_DIR/Airodump_Merged_${RANGE_LABEL}.csv"
    echo "${new_header_line},Source File" > "$OUTPUT_AIRODUMP_FILE"

    # Create a comma-separated string of indices to keep (e.g., "1,2,4,5")
    keep_indices_str=$(IFS=, ; echo "${keep_indices[*]}")

    # Process each file
    for file in "$INPUT_AIRODUMP_DIR"/*.log.csv; do
        # Skip the header (tail -n +2) and remove carriage returns,
        # then use awk to print only the desired fields plus the source file at the end.
        tail -n +2 "$file" | tr -d '\r' | awk -F, -v OFS="," -v keep="$keep_indices_str" -v src="$file" '
        BEGIN { n = split(keep, arr, ","); }
        {
            out = "";
            for(i = 1; i <= n; i++){
                idx = arr[i] + 0;
                if(idx <= NF) {
                out = (out == "" ? $idx : out OFS $idx);
                }
            }
            print out, src;
        }' >> "$OUTPUT_AIRODUMP_FILE"
    done

    echo "Airodump logs merged into $OUTPUT_AIRODUMP_FILE"
fi