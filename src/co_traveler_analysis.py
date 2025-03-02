#!/usr/bin/env python3
"""
co_traveler_analysis.py
This script analyzes the merged data produced by the merge process and:
  1. Prompts the user for a date range (in DD-MM-YYYY format) to filter the data. If the user declines,
     all available merged files (from BR-Lite/Processing/Merges) are analyzed.
  2. Loads all qualifying merged CSV files into a DataFrame and normalizes the columns in a case‑insensitive
     manner so that:
         - "firstseen" is renamed to "time"
         - "currentlatitude" and "currentlongitude" are renamed to "latitude" and "longitude"
         - The columns "altitudemeters" and "accuracymeters" (or "accuracy meters") are dropped.
     The "source file" column is retained.
  3. Groups records by unique signals (using mac and ssid, with blank ssid replaced by "unk") and collects
     the unique source files for each group.
  4. Classifies each group:
       - Potential co-traveler: if any two records are ≥1000m apart.
       - Potential Static: if all records are within 300m of each other.
       - Otherwise, Unknown.
     The earliest and latest time values in each group are recorded as first seen and last seen.
  5. For groups classified as static, computes a best-guess GPS coordinate using a weighted average based on rssi.
  6. Saves a categorized CSV file (with MAC, SSID, AUTHMODE, TIME, CHANNEL, RSSI, LATITUDE, LONGITUDE, TYPE, SOURCE FILE,
     CLASSIFICATION, FIRST SEEN, LAST SEEN, and aggregated SOURCE FILE(S) for each signal) in the outputs folder,
     with all column headers in ALL CAPS.
  7. Generates an interactive HTML map for co-traveler data:
       - For each potential co-traveler group, local clustering is performed (merging points within 50m into a single aggregated marker).
       - Aggregated markers are grouped into layers based on their "FURTHEST DETECTION DISTANCE" bin:
         1-5km, 5-10km, 10-15km, 15-20km, and >20km.
       - Each bin is assigned a discrete color (green, blue, purple, orange, red, respectively), which is used for the markers.
       - Markers are added to a MarkerCluster within each bin’s FeatureGroup so that users can toggle marker visibility per bin.
       - Popup text displays <b>MAC</b>, <b>SSID</b>, <b>FIRST SEEN</b>, <b>LAST SEEN</b>, <b>SOURCE FILE(S)</b>, and 
         <b>FURTHEST DETECTION DISTANCE</b> (in km).
"""

import os
import sys
import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import folium
from folium.plugins import MarkerCluster
from folium import FeatureGroup, LayerControl

# -----------------------------
# Helper functions
# -----------------------------
def haversine(lat1, lon1, lat2, lon2):
    """Compute the great-circle distance (in meters) between two points."""
    R = 6371000  # meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%d-%m-%Y")
    except Exception as e:
        print(f"Error parsing date '{date_str}': {e}")
        sys.exit(1)

def average_rssi(rssi_str):
    try:
        parts = rssi_str.split("|")
        vals = [float(x) for x in parts if x.strip() != ""]
        return sum(vals) / len(vals) if vals else None
    except Exception:
        return None

def cluster_records(records, threshold=50):
    clusters = []
    indices = records.index.tolist()
    while indices:
        current_idx = indices.pop(0)
        cluster = [current_idx]
        changed = True
        center_lat = records.loc[current_idx, "latitude"]
        center_lon = records.loc[current_idx, "longitude"]
        while changed:
            changed = False
            remove_list = []
            for idx in indices:
                d = haversine(center_lat, center_lon, records.loc[idx, "latitude"], records.loc[idx, "longitude"])
                if d <= threshold:
                    cluster.append(idx)
                    remove_list.append(idx)
                    changed = True
            for idx in remove_list:
                indices.remove(idx)
            if cluster:
                center_lat = records.loc[cluster, "latitude"].mean()
                center_lon = records.loc[cluster, "longitude"].mean()
        clusters.append(cluster)
    return clusters

def aggregate_cluster(records, cluster_indices):
    clust_data = records.loc[cluster_indices]
    center_lat = clust_data["latitude"].mean()
    center_lon = clust_data["longitude"].mean()
    first_seen = clust_data["time_dt"].min()
    last_seen = clust_data["time_dt"].max()
    src_files = ", ".join(sorted(set(clust_data["source file"].astype(str))))
    return {"center": (center_lat, center_lon), "first_seen": first_seen, "last_seen": last_seen, "source_files": src_files}

def get_bin_label(max_dist):
    if max_dist < 5000:
        return "1-5km"
    elif max_dist < 10000:
        return "5-10km"
    elif max_dist < 15000:
        return "10-15km"
    elif max_dist < 20000:
        return "15-20km"
    else:
        return ">20km"

# -----------------------------
# Discrete color mapping for bins (using folium icon color names).
# -----------------------------
bin_colors = {
    "1-5km": "green",
    "5-10km": "blue",
    "10-15km": "purple",
    "15-20km": "orange",
    ">20km": "red"
}

# -----------------------------
# Set directories.
# -----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGES_DIR = os.path.join(BASE_DIR, "Processing", "Merges")
OUTPUTS_DIR = os.path.join(BASE_DIR, "Outputs")

# -----------------------------
# Step 1: Prompt for date range.
# -----------------------------
use_range = input("Do you wish to specify a date range for co-traveler Analysis? (y/n): ").strip().lower()
date_filter = False
if use_range == 'y':
    start_input = input("Enter beginning date (DD-MM-YYYY): ").strip()
    end_input = input("Enter ending date (DD-MM-YYYY): ").strip()
    start_dt = parse_date(start_input).replace(hour=0, minute=0, second=0)
    end_dt = parse_date(end_input).replace(hour=23, minute=59, second=59)
    print(f"Date range specified: {start_dt} to {end_dt}")
    date_filter = True
else:
    print("Analyzing all available data.")

# -----------------------------
# Step 2: Load merged CSV files.
# -----------------------------
import re
merged_files = [os.path.join(MERGES_DIR, f) for f in os.listdir(MERGES_DIR)
                if "wigled" in f.lower() and "merged" in f.lower() and f.lower().endswith(".csv")]
if not merged_files:
    print("No merged CSV files found in Processing/Merges. Exiting.")
    sys.exit(1)
if date_filter:
    filtered_files = []
    for f in merged_files:
        m = re.search(r'(\d{2}-\d{2}-\d{4})', os.path.basename(f))
        if m:
            file_date_str = m.group(1)
            file_date = parse_date(file_date_str)
            if start_dt.date() <= file_date.date() <= end_dt.date():
                filtered_files.append(f)
        else:
            print(f"Filename {os.path.basename(f)} does not contain a valid date, skipping.")
    if not filtered_files:
        print("No merged CSV files found in the specified date range. Exiting.")
        sys.exit(1)
    merged_files = filtered_files

dfs = []
for f in merged_files:
    try:
        temp_df = pd.read_csv(f, low_memory=False)
        dfs.append(temp_df)
    except Exception as e:
        print(f"Error reading {f}: {e}")
if not dfs:
    print("No data loaded from merged CSV files. Exiting.")
    sys.exit(1)
df = pd.concat(dfs, ignore_index=True)
print(f"Loaded {len(df)} records from {len(merged_files)} merged file(s).")

# -----------------------------
# Step 3: Normalize columns (case-insensitive).
# -----------------------------
df.columns = [col.strip().lower() for col in df.columns]
rename_map = {}
if "firstseen" in df.columns and "time" not in df.columns:
    rename_map["firstseen"] = "time"
if "currentlatitude" in df.columns and "latitude" not in df.columns:
    rename_map["currentlatitude"] = "latitude"
if "currentlongitude" in df.columns and "longitude" not in df.columns:
    rename_map["currentlongitude"] = "longitude"
if rename_map:
    df.rename(columns=rename_map, inplace=True)
drop_cols = [col for col in df.columns if col in ["altitudemeters", "accuracymeters", "accuracy meters"]]
if drop_cols:
    df.drop(columns=drop_cols, inplace=True)
expected_cols = ["mac", "ssid", "authmode", "time", "channel", "rssi", "latitude", "longitude", "type", "source file"]
for col in expected_cols:
    if col not in df.columns:
        print(f"Expected column '{col}' not found in CSV. Detected columns: {df.columns.tolist()}")
        sys.exit(1)

# -----------------------------
# Step 4: Data preprocessing.
# -----------------------------
df["time_dt"] = pd.to_datetime(df["time"], errors="coerce")
df = df[(df["latitude"] != 0) & (df["longitude"] != 0)]
if date_filter:
    df = df[(df["time_dt"] >= start_dt) & (df["time_dt"] <= end_dt)]
    if df.empty:
        print("No data found in the specified date range after filtering. Exiting.")
        sys.exit(1)

# -----------------------------
# Step 4a: Filter out whitelisted MACs and SSIDs.
# -----------------------------
whitelist_file = os.path.join(BASE_DIR, "Whitelist.csv")
if os.path.exists(whitelist_file):
    # Load the whitelist CSV and build a set of items to exclude.
    whitelist_df = pd.read_csv(whitelist_file)
    whitelist_items = set()
    for col in whitelist_df.columns:
        # Convert each value to a lowercase string and add to the set.
        items = whitelist_df[col].dropna().astype(str).str.strip().str.lower().tolist()
        whitelist_items.update(items)
    initial_count = len(df)
    # Filter out any records where the 'mac' or 'ssid' (converted to lowercase) is in the whitelist.
    df = df[~(df["mac"].str.lower().isin(whitelist_items) | df["ssid"].str.lower().isin(whitelist_items))]
    filtered_out = initial_count - len(df)
    print(f"Filtered out {filtered_out} records based on Whitelist.")
else:
    print("Whitelist.csv not found in the base directory; proceeding without whitelist filtering.")



# -----------------------------
# Step 5: Group by unique signals and classify.
# -----------------------------
df["ssid_filled"] = df["ssid"].replace("", "unk")
classified = []
cotraveler_groups = {}
static_groups = {}
for (mac, ssid), group in df.groupby(["mac", "ssid_filled"]):
    records = group.copy()
    coords = list(zip(records["latitude"], records["longitude"]))
    times = records["time_dt"].tolist()
    if "source file" in group.columns:
        source_files = ", ".join(sorted(set(group["source file"].astype(str))))
    else:
        source_files = "n/a"
    if len(coords) < 2:
        classification = "unknown"
        group_max = 0
    else:
        is_cotraveler = False
        max_dist = 0
        for i in range(len(coords)):
            for j in range(i+1, len(coords)):
                d = haversine(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
                if d >= 1000:
                    is_cotraveler = True
                if d > max_dist:
                    max_dist = d
        group_max = max_dist
        if is_cotraveler:
            classification = "co-traveler"
        elif max_dist <= 300:
            classification = "static"
        else:
            classification = "unknown"
    first_seen = min(times)
    last_seen = max(times)
    classified.append({
        "mac": mac,
        "ssid": ssid,
        "classification": classification,
        "first seen": first_seen,
        "last seen": last_seen,
        "source files": source_files,
        "max_dist": group_max
    })
    if classification == "co-traveler":
        cotraveler_groups[(mac, ssid)] = {"records": records, "max_dist": group_max}
    elif classification == "static":
        static_groups[(mac, ssid)] = records
classified_df = pd.DataFrame(classified)

# -----------------------------
# Step 6: Compute best-guess GPS coordinates for static signals.
# -----------------------------
static_results = []
for key, group in static_groups.items():
    group = group.copy()
    group["avg_rssi"] = group["rssi"].apply(average_rssi)
    group["weight"] = group["avg_rssi"].apply(lambda x: max(0, 130 + x) if x is not None else 0)
    total_weight = group["weight"].sum()
    if total_weight > 0:
        best_lat = (group["latitude"] * group["weight"]).sum() / total_weight
        best_lon = (group["longitude"] * group["weight"]).sum() / total_weight
    else:
        best_lat = group["latitude"].mean()
        best_lon = group["longitude"].mean()
    static_results.append({
        "mac": key[0],
        "ssid": key[1],
        "best_lat": best_lat,
        "best_lon": best_lon
    })
static_df = pd.DataFrame(static_results)

# -----------------------------
# Step 7: Save categorized signals CSV with all headers in ALL CAPS.
# -----------------------------
categorized = classified_df.copy()
categorized["best_lat"] = ""
categorized["best_lon"] = ""
for idx, row in categorized.iterrows():
    if row["classification"] == "static":
        match = static_df[(static_df["mac"] == row["mac"]) & (static_df["ssid"] == row["ssid"])]
        if not match.empty:
            categorized.at[idx, "best_lat"] = match.iloc[0]["best_lat"]
            categorized.at[idx, "best_lon"] = match.iloc[0]["best_lon"]
if "max_dist" in categorized.columns:
    categorized.drop(columns=["max_dist"], inplace=True)
categorized.columns = [col.upper() for col in categorized.columns]
output_csv = os.path.join(OUTPUTS_DIR, "CATEGORIZED_SIGNALS.csv")
categorized.to_csv(output_csv, index=False)
print(f"Categorized signals saved to {output_csv}")

# -----------------------------
# Step 8: Generate interactive HTML map for co-traveler groups.
# -----------------------------
arcgis_tiles = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

# First pass: For each co-traveler group, perform local clustering (points within 50m) and aggregate markers.
aggregated_markers = []
for key, group_info in cotraveler_groups.items():
    mac, ssid = key
    records = group_info["records"].copy().sort_values(by="time_dt")
    clusters = cluster_records(records, threshold=50)
    for clust in clusters:
        agg = aggregate_cluster(records, clust)
        first_seen = records.loc[clust, "time_dt"].min()
        last_seen = records.loc[clust, "time_dt"].max()
        src_files = ", ".join(sorted(set(records.loc[clust, "source file"].astype(str))))
        aggregated_markers.append({
            "mac": mac,
            "ssid": ssid,
            "latitude": agg["center"][0],
            "longitude": agg["center"][1],
            "first_seen": first_seen,
            "last_seen": last_seen,
            "source_files": src_files,
            "max_dist": group_info["max_dist"]
        })

# Group aggregated markers by their max_dist bin.
bins_agg = {}
for marker in aggregated_markers:
    bin_label = get_bin_label(marker["max_dist"])
    if bin_label not in bins_agg:
        bins_agg[bin_label] = []
    bins_agg[bin_label].append(marker)

# Create a separate FeatureGroup (with its own MarkerCluster) for each bin.
co_map = folium.Map(location=[records["latitude"].mean(), records["longitude"].mean()], zoom_start=10, tiles=arcgis_tiles, attr="ArcGIS World Imagery")
for bin_label, markers in bins_agg.items():
    fg = FeatureGroup(name=f"FURTHEST {bin_label.upper()}")
    cluster = MarkerCluster().add_to(fg)
    assigned_color = bin_colors[bin_label]
    for marker in markers:
        popup_text = (
            f"<b>MAC:</b> {marker['mac'].upper()}<br>"
            f"<b>SSID:</b> {marker['ssid'].upper() if marker['ssid'] != '' else 'UNK'}<br>"
            f"<b>FIRST SEEN:</b> {marker['first_seen']}<br>"
            f"<b>LAST SEEN:</b> {marker['last_seen']}<br>"
            f"<b>SOURCE FILE(S):</b> {marker['source_files'].upper()}<br>"
            f"<b>FURTHEST DETECTION DISTANCE:</b> {round(marker['max_dist']/1000.0, 1)} km"
        )
        folium.Marker(
            location=[marker["latitude"], marker["longitude"]],
            popup=popup_text,
            icon=folium.Icon(color=assigned_color)
        ).add_to(cluster)
    fg.add_to(co_map)
LayerControl().add_to(co_map)
co_map_file = os.path.join(OUTPUTS_DIR, "COTRAVELER_MAP.html")
co_map.save(co_map_file)
print(f"co-traveler map saved to {co_map_file}")

print("co-traveler Analysis complete.")
