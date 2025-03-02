#!/bin/bash

set -e  # exit on error
set -u  # treat unset variables as errors

# This script verifies and creates necessary directories, updates
# system dependencies, installs required packages, and fixes permissions
# on scripts.
#
# Directory structure assumed (relative to the repo root folder):
# /
#   data/
#     input/
#       kismetdb/
#       airodump_logs/
#       archive/
#     processed/
#       kismet/
#       airodump/
#       merges/
#     output/

# echo "Installing dependencies..."
# sudo apt-get update && apt-get install -y \
#     python3 \
#     python3-pip \
#     python3-pandas \
#     python3-numpy \
#     python3-folium \
#     jq \
#     yq

echo "Ensuring all .sh and .py scripts are executable..."
find ./src -maxdepth 1 -type f \( -name "*.sh" -o -name "*.py" \) -exec chmod +x {} +

echo "Creating config.yaml..."
echo "INPUT_KISMET_DIR: $(pwd)/data/input/kismetdb" > config.yaml
echo "INPUT_AIRODUMP_DIR: $(pwd)/data/input/airodump_logs" >> config.yaml
echo "INPUT_ARCHIVE_DIR: $(pwd)/data/input/archive" >> config.yaml
echo "PROCESSED_KISMET_DIR: $(pwd)/data/processed/kismet" >> config.yaml
echo "PROCESSED_AIRODUMP_DIR: $(pwd)/data/processed/airodump" >> config.yaml
echo "PROCESSED_MERGES_DIR: $(pwd)/data/processed/merges" >> config.yaml
echo "OUTPUT_DIR: $(pwd)/data/output" >> config.yaml
echo "WHITELIST_FILE: $(pwd)/whitelist.csv" >> config.yaml

# directories to check/create
for key in $(yq e 'keys | .[]' config.yaml); do
  export "$key=$(yq e ".$key" config.yaml)"
done

DIRECTORIES=(
    $INPUT_KISMET_DIR
    $INPUT_AIRODUMP_DIR
    $INPUT_ARCHIVE_DIR
    $PROCESSED_KISMET_DIR
    $PROCESSED_AIRODUMP_DIR
    $PROCESSED_MERGES_DIR
    $OUTPUT_DIR
)

echo "Ensuring data directories exist..."
for DIR in "${DIRECTORIES[@]}"; do
    mkdir -p "$DIR"
done

echo "Ensuring whitelist.csv file exists..."
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "Device Name,Device Type,Wifi MAC Address,Bluetooth MAC Address,Randomized Wifi,Randomized BT" > $WHITELIST_FILE
fi

echo "Setup complete."
