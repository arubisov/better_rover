#!/bin/bash
#
# BR-Lite Source Data Processing Script (process_source.sh)
#
# This script performs the following:
#   1. Updates permissions in the Input_Data directory (and its subdirectories)
#      to remove any read-only restrictions.
#   2. Prompts the user to confirm that all source data files conform to a 
#      SENSOR_NAME-YYYY-MM-DD naming convention for both Airodump and Kismet files.
#      If the user does not confirm, the script exits.
#   3. Checks whether Kismet or Airodump outputs have already been processed.
#      If outputs exist, it prompts the user whether to re-run conversions.
#         - If the user answers "y": all conversions will be re-run (overwriting any outputs).
#         - If the user answers "n": each conversion step is only performed if its output file does not exist.
#   4. Processes Kismet files:
#       - For each .kismet file in Input_Data/Kismetdb,
#         creates a subdirectory in Processing/Kismet named after the file (without extension)
#       - Converts the .kismet file into three outputs:
#           a) WigleCSV output (appending "_wigled.csv" to the base filename)
#           b) Packet data CSV output (appending "_packetdata.csv" to the base filename)
#           c) pcap file (appending "_pcap.pcapng" to the base filename)
#
#   5. Processes Airodump files:
#       - For each *.log.csv file in Input_Data/Airodump_Logs,
#         it reads the file’s LocalTime column to determine the earliest and latest timestamps,
#         reformats these timestamps, and copies the file to Processing/Airodump
#         with a modified filename that appends the timestamp range.
#
# Assumptions:
#   - The BR-Lite base directory is the parent of FIDIM.
#   - Airodump CSV files have a header with a "LocalTime" column in "YYYY-MM-DD HH:MM:SS" format.
#

# load vars from config
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
CONFIG_PATH="$SCRIPT_DIR/../config.yaml"
for key in $(yq e 'keys | .[]' $CONFIG_PATH); do
  export "$key=$(yq e ".$key" $CONFIG_PATH)"
done

# 1. Update permissions for all files in the Input_Data directory
echo "Updating permissions in Input_Data..."
sudo chmod -R u+rw "$BASE_DIR/Input_Data"

# 2. Confirm naming convention compliance before proceeding.
read -p "Confirm all source data files conform to a SENSOR_NAME-YYYY-MM-DD format for both Airodump and Kismet files. Failure to properly tag source data file by collected sensors will produce unintelligible analytics.
Confirmed? y/n: " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Exiting BR-Lite. When ready, restart the program."
    exit 1
fi


# Determine conversion mode:
# If there are existing outputs, prompt the user:
#   - "y": re-run conversions for all files (overwrite)
#   - "n": only process missing outputs.
if [ "$existing_outputs" = true ]; then
    read -p "Extract all files? This will re-process all files in the Input_Data folders and overwriting their contents. y/n: " rerun
    if [[ "$rerun" =~ ^[Yy]$ ]]; then
        re_run_all="y"
    else
        re_run_all="n"
    fi
else
    re_run_all="y"
fi

# 4. Process Kismet Files
echo "Processing Kismet files..."
KISMET_SRC_DIR="$BASE_DIR/Input_Data/Kismetdb"
if [ -d "$KISMET_SRC_DIR" ]; then
    for kismet_file in "$KISMET_SRC_DIR"/*.kismet; do
        if [ -f "$kismet_file" ]; then
            base=$(basename "$kismet_file" .kismet)
            dest_dir="$KISMET_PROC_DIR/$base"
            mkdir -p "$dest_dir"
            
            # Define expected output filenames
            output1="$dest_dir/${base}_wigled.csv"
            output2="$dest_dir/${base}_packetdata.ek.json"
            output3="$dest_dir/${base}_pcap.pcapng"
            output4="$dest_dir/${base}_packetdata.json"   # Fixed variable assignment

            echo "Processing Kismet file: $kismet_file"

            # Output 1: Convert to WigleCSV
            if [ "$re_run_all" = "y" ] || [ ! -f "$output1" ]; then
                echo "Converting to wiglecsv: $output1"
                sudo kismetdb_to_wiglecsv --force --in "$kismet_file" --out "$output1" 
            else
                echo "Skipping wigle conversion for $kismet_file as output $output1 already exists."
            fi

            # Output 2: Extract packet data to EKJSON (ELK Stack Usable)
            if [ "$re_run_all" = "y" ] || [ ! -f "$output2" ]; then
                echo "Converting unified Kismet files into JSON formats: $output2"
                sudo kismetdb_dump_devices -ekjson --in "$kismet_file" --out "$output2"                
            else
                echo "Skipping packet data extraction for $kismet_file as output $output2 already exists."
            fi

            # Output 4: Extract packet data to JSON
            if [ "$re_run_all" = "y" ] || [ ! -f "$output4" ]; then
                echo "Converting unified Kismet files into JSON formats: $output4"
                sudo kismetdb_dump_devices --in "$kismet_file" --out "$output4"
            fi

            # Output 3: Convert to pcap (pcapng format)
            if [ "$re_run_all" = "y" ] || [ ! -f "$output3" ]; then
                echo "Converting to pcap: $output3"
                sudo kismetdb_to_pcap --in "$kismet_file" --out "$output3"
            else
                echo "Skipping pcap conversion for $kismet_file as output $output3 already exists."
            fi

            echo "Finished processing Kismet file: $kismet_file"
        fi
    done
else
    echo "Kismet source directory ($KISMET_SRC_DIR) does not exist. Skipping Kismet processing."
fi

echo "Processing Airodump files..."
AIRODUMP_SRC_DIR="$BASE_DIR/Input_Data/Airodump_Logs"
if [ -d "$AIRODUMP_SRC_DIR" ]; then
    for airodump_file in "$AIRODUMP_SRC_DIR"/*.log.csv; do
        if [ -f "$airodump_file" ]; then
            echo "Processing airodump file: $airodump_file"
            # Extract earliest and latest timestamps from the LocalTime column using awk.
            read earliest latest < <(awk -F, 'NR==1 {
                    for(i=1;i<=NF;i++){
                        if($i=="LocalTime"){
                            col=i; break
                        }
                    }
                }
                NR>1 {
                    timeVal = $(col)
                    if(min=="") { min = timeVal; max = timeVal }
                    else {
                        if(timeVal < min) min = timeVal
                        if(timeVal > max) max = timeVal
                    }
                }
                END { print min, max }' "$airodump_file")
            
            # Verify that timestamps were found
            if [ -z "$earliest" ] || [ -z "$latest" ]; then
                echo "Could not determine timestamps for $airodump_file. Skipping."
                continue
            fi
            
            # Format timestamps: Replace space with dash and remove colons.
            earliest_fmt=$(echo "$earliest" | sed 's/ /-/; s/://g')
            latest_fmt=$(echo "$latest" | sed 's/ /-/; s/://g')
            
            base=$(basename "$airodump_file" .log.csv)
            output_file="$AIRODUMP_PROC_DIR/${base}_${earliest_fmt}-${latest_fmt}.log.csv"
            
            if [ "$re_run_all" = "y" ] || [ ! -f "$output_file" ]; then
                echo "Copying airodump file to: $output_file"
                sudo cp "$airodump_file" "$output_file"
            else
                echo "Skipping airodump file $airodump_file as output $output_file already exists."
            fi
        fi
    done
else
    echo "Airodump source directory ($AIRODUMP_SRC_DIR) does not exist. Skipping Airodump processing."
fi

echo "Source data processing complete."
