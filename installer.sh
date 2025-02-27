#!/bin/bash
#
# BR-Lite Installer Script (updated)
#
# This script verifies and creates necessary directories, updates
# system dependencies, installs required packages, and fixes permissions
# on scripts in the FIDIM directory.
#
# Directory structure assumed (relative to the BR-Lite folder):
#   Input_Data/
#       Kismetdb
#       Airodump_Logs
#       Archive
#   Processing/
#       Kismet
#       Airodump
#       Merges
#   Outputs
#
# This installer is located in X/BR-Lite/FIDIM/
# so the BR-Lite base directory is one level up from FIDIM.

# Use realpath to determine the base directory robustly.
BASE_DIR="$(realpath "$(dirname "$0")/../")"
echo "BR-Lite base directory: $BASE_DIR"

# Define the directories to check/create (relative to BASE_DIR)
DIRECTORIES=(
    "$BASE_DIR/Input_Data/Kismetdb"
    "$BASE_DIR/Input_Data/Airodump_Logs"
    "$BASE_DIR/Input_Data/Archive"
    "$BASE_DIR/Processing/Kismet"
    "$BASE_DIR/Processing/Airodump"
    "$BASE_DIR/Processing/Merges"
    "$BASE_DIR/Outputs"
)

# Check for existence and create missing directories in the BR-Lite base directory.
for DIR in "${DIRECTORIES[@]}"; do
    if [ ! -d "$DIR" ]; then
        echo "Creating directory: $DIR"
        mkdir -p "$DIR"
    else
        echo "Directory already exists: $DIR"
    fi
done

# Prompt user to update system dependencies
read -p "Update system dependencies? If this is a first time install of BR-Lite, this is recommended. y/n: " ANSWER
if [[ "$ANSWER" =~ ^[Yy]$ ]]; then
    echo "Updating system dependencies..."
    sudo apt update && sudo apt upgrade -y
else
    echo "Skipping system dependency update."
fi

# -----------------------------
# Install required system packages
# -----------------------------
echo "Checking for required system packages..."

# List of required system packages
SYS_PACKAGES=(python3 python3-pip)

for pkg in "${SYS_PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        echo "$pkg is not installed. Installing $pkg..."
        sudo apt-get install -y "$pkg"
    else
        echo "$pkg is already installed."
    fi
done

# -----------------------------
# Install required Python packages via apt (or pip, as preferred)
# -----------------------------
echo "Installing/updating required Python packages (pandas, numpy, folium)..."
sudo apt install python3-pandas python3-numpy python3-folium -y

echo "Installing JSON dependencies"
sudo apt install jq -y

echo "Autoremoving non-essential dependencies..."
sudo apt autoremove
# -----------------------------
# Update permissions for scripts in the FIDIM directory
# -----------------------------
echo "Updating permissions for all .sh and .py scripts in the FIDIM directory..."
find "$(dirname "$0")" -maxdepth 1 -type f \( -name "*.sh" -o -name "*.py" \) -exec chmod +x {} \;
echo "Script permissions updated."

echo "BR-Lite installation process complete."
