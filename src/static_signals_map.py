#!/usr/bin/env python3
"""
static_signals_map.py

This script creates an interactive map for static signals using the aggregated static signals CSV.
It:
  - Finds the most recent aggregated static signals CSV (matching STATIC_SIGNALS-*.csv) in the Processing/Merges folder.
  - Loads the CSV and, if necessary, adds an AUTHMODE column with a default value.
  - Groups the data by AUTHMODE.
  - Assigns each AuthMode a discrete color from a preset palette.
  - Uses folium’s MarkerCluster within a separate FeatureGroup for each AuthMode.
  - Sets each marker’s popup to display bold labels for MAC, SSID, FIRST SEEN, LAST SEEN, and AUTHMODE.
  - Sanitizes text fields to avoid JavaScript escape issues.
  - Saves the resulting map as STATIC_SIGNALS_MAP.html in the Outputs directory.
"""

import os
import sys
import glob
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from folium import FeatureGroup, LayerControl

def sanitize_text(text):
    """Escape backslashes and other problematic characters for safe insertion into template strings."""
    if pd.isna(text):
        return ""
    # Encode as unicode_escape then decode to string.
    try:
        return str(text).encode('unicode_escape').decode('utf-8')
    except Exception:
        return str(text)

# Set directories.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGES_DIR = os.path.join(BASE_DIR, "Processing", "Merges")
OUTPUTS_DIR = os.path.join(BASE_DIR, "Outputs")

# Find the most recent aggregated static signals CSV in Processing/Merges.
pattern = os.path.join(MERGES_DIR, "STATIC_SIGNALS-*.csv")
csv_files = glob.glob(pattern)
if not csv_files:
    print(f"No aggregated static signals CSV found matching pattern {pattern}. Exiting.")
    sys.exit(1)
csv_files.sort(key=os.path.getmtime, reverse=True)
aggregated_csv = csv_files[0]
print(f"Using aggregated static signals CSV: {aggregated_csv}")

# Load the aggregated CSV (headers are expected to be in ALL CAPS).
try:
    df = pd.read_csv(aggregated_csv)
except Exception as e:
    print(f"Error loading CSV: {e}")
    sys.exit(1)

# If the AUTHMODE column is missing, add it with a default value.
if "AUTHMODE" not in df.columns:
    df["AUTHMODE"] = "UNKNOWN"

# Group by AuthMode.
auth_modes = df["AUTHMODE"].unique()

# Define a fixed palette for AuthModes.
palette = ["blue", "green", "orange", "purple", "red", "cadetblue", "darkred"]
auth_mode_colors = {}
for i, mode in enumerate(auth_modes):
    auth_mode_colors[mode] = palette[i % len(palette)]
print("Creating AuthMode color mapping:")

# Create a base map centered on the average best-guess location.
if "BEST_LAT" in df.columns and "BEST_LON" in df.columns:
    center_lat = df["BEST_LAT"].mean()
    center_lon = df["BEST_LON"].mean()
else:
    center_lat = df["LATITUDE"].mean()
    center_lon = df["LONGITUDE"].mean()

m = folium.Map(location=[center_lat, center_lon], zoom_start=12,
               tiles="https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
               attr="ArcGIS World Imagery")

# For each AuthMode, create a FeatureGroup with its own MarkerCluster.
for mode, color in auth_mode_colors.items():
    fg = FeatureGroup(name=f"AUTHMODE: {sanitize_text(mode)}", show=True)
    cluster = MarkerCluster().add_to(fg)
    mode_df = df[df["AUTHMODE"] == mode]
    for _, row in mode_df.iterrows():
        lat = row["BEST_LAT"] if "BEST_LAT" in row and not pd.isna(row["BEST_LAT"]) else row["LATITUDE"]
        lon = row["BEST_LON"] if "BEST_LON" in row and not pd.isna(row["BEST_LON"]) else row["LONGITUDE"]
        popup_text = (
            f"<b>MAC:</b> {sanitize_text(row['MAC'].upper())}<br>"
            f"<b>SSID:</b> {sanitize_text(row['SSID'].upper() if row['SSID'] != '' else 'UNK')}<br>"
            f"<b>FIRST SEEN:</b> {sanitize_text(row['FIRST_SEEN'])}<br>"
            f"<b>LAST SEEN:</b> {sanitize_text(row['LAST_SEEN'])}<br>"
            f"<b>AUTHMODE:</b> {sanitize_text(row['AUTHMODE'].upper())}"
        )
        folium.Marker(
            location=[lat, lon],
            popup=popup_text,
            icon=folium.Icon(color=color, icon_color="black")
        ).add_to(cluster)
    fg.add_to(m)

LayerControl().add_to(m)

# Save the static signals map to the Outputs directory.
map_path = os.path.join(OUTPUTS_DIR, "STATIC_SIGNALS_MAP.html")
m.save(map_path)
print(f"Static signals map saved to {map_path}")
