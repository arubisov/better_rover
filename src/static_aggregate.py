#!/usr/bin/env python3
"""
static_aggregate.py

This script aggregates static signals from the most recent Wigled_Merged_*.csv data in the Processing/Merges directory.
A group (by MAC and SSID) is classified as static if all its GPS records (using LATITUDE and LONGITUDE) are within 200 meters of one another.
For each static group, the script computes a best-guess location using a weighted average of the coordinates (weight = max(0, 130 + RSSI)).
The earliest and latest detection times are determined from the TIME column.
AuthMode and Source File are also retained.
The aggregated output is saved as "STATIC_SIGNALS-YYYYMMDD.csv" (with today’s date in YYYYMMDD format)
to both the Outputs and Processing/Merges directories.
"""

import os
import sys
import glob
import pandas as pd
from datetime import datetime
import shutil
import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Define directories (assuming this script is executed from BR-Lite/FIDIM)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS_DIR = os.path.join(BASE_DIR, "Outputs")
MERGES_DIR = os.path.join(BASE_DIR, "Processing", "Merges")

# Step 1: Copy the categorized signals CSV from Outputs to Processing/Merges.
categorized_pattern = os.path.join(OUTPUTS_DIR, "*CATEGORIZED_SIGNALS*.csv")
categorized_files = glob.glob(categorized_pattern)
if not categorized_files:
    print("No categorized signals CSV found in Outputs. Exiting.")
    sys.exit(1)
categorized_files.sort(key=os.path.getmtime, reverse=True)
latest_categorized = categorized_files[0]
dest_file = os.path.join(MERGES_DIR, os.path.basename(latest_categorized))
shutil.copy2(latest_categorized, dest_file)
print(f"Copied {latest_categorized} to {dest_file}")

# Step 2: Merge all Wigled_Merged_*.csv files in Processing/Merges.
merged_files = [os.path.join(MERGES_DIR, f) for f in os.listdir(MERGES_DIR)
                if f.startswith("Wigled_Merged_") and f.lower().endswith(".csv")]
if not merged_files:
    print("No Wigled_Merged_*.csv files found in Processing/Merges. Exiting.")
    sys.exit(1)

dfs = []
for f in merged_files:
    try:
        df = pd.read_csv(f)
        dfs.append(df)
    except Exception as e:
        print(f"Error reading {f}: {e}")
if not dfs:
    print("No data loaded from CSV files. Exiting.")
    sys.exit(1)
merged_df = pd.concat(dfs, ignore_index=True)
print(f"Merged {len(merged_df)} records from {len(merged_files)} files.")

# Step 3: Normalize column names to uppercase.
merged_df.columns = [col.strip().upper() for col in merged_df.columns]

# Normalize location column names for Wigled_Merged files:
# Wigled files label latitude as CurrentLatitude and longitude as CurrentLongitude.
if "CURRENTLATITUDE" in merged_df.columns:
    merged_df.rename(columns={"CURRENTLATITUDE": "LATITUDE"}, inplace=True)
if "CURRENTLONGITUDE" in merged_df.columns:
    merged_df.rename(columns={"CURRENTLONGITUDE": "LONGITUDE"}, inplace=True)

# Normalize time column names: Wigled files use "FirstSeen" for time.
if "TIME" not in merged_df.columns and "FIRSTSEEN" in merged_df.columns:
    merged_df.rename(columns={"FIRSTSEEN": "TIME"}, inplace=True)

# Drop unwanted columns: ALTITUDEMETERS and ACCURACYMETERS.
for col in ["ALTITUDEMETERS", "ACCURACYMETERS"]:
    if col in merged_df.columns:
        merged_df.drop(columns=[col], inplace=True)

# Step 4: Re-assess static signals.
# For each group (by MAC and SSID), compute the maximum pairwise distance using LATITUDE and LONGITUDE.
grouped = merged_df.groupby(["MAC", "SSID"])
aggregated_records = []
for (mac, ssid), group in grouped:
    try:
        lats = group["LATITUDE"].astype(float).tolist()
        lons = group["LONGITUDE"].astype(float).tolist()
    except KeyError:
        print(f"Group for MAC {mac} and SSID {ssid} does not contain proper location data. Skipping.")
        continue
    max_dist = 0
    n = len(lats)
    if n > 1:
        for i in range(n):
            for j in range(i+1, n):
                d = haversine(lats[i], lons[i], lats[j], lons[j])
                if d > max_dist:
                    max_dist = d
    # Only include groups where max distance is <= 200 meters.
    if max_dist <= 200:
        # Compute best-guess location using weighted average.
        if "BEST_LAT" in group.columns and "BEST_LON" in group.columns:
            lat_vals = group["BEST_LAT"].astype(float)
            lon_vals = group["BEST_LON"].astype(float)
        else:
            lat_vals = group["LATITUDE"].astype(float)
            lon_vals = group["LONGITUDE"].astype(float)
        # Use weighted average based on RSSI.
        group["RSSI"] = pd.to_numeric(group["RSSI"], errors="coerce")
        group["WEIGHT"] = group["RSSI"].apply(lambda x: max(0, 130 + x) if pd.notna(x) else 1)
        total_weight = group["WEIGHT"].sum()
        if total_weight > 0:
            best_lat = (lat_vals * group["WEIGHT"]).sum() / total_weight
            best_lon = (lon_vals * group["WEIGHT"]).sum() / total_weight
        else:
            best_lat = lat_vals.mean()
            best_lon = lon_vals.mean()
        # Compute FIRST_SEEN and LAST_SEEN from the TIME column.
        group["TIME_DT"] = pd.to_datetime(group["TIME"], errors="coerce")
        first_seen = group["TIME_DT"].min()
        last_seen = group["TIME_DT"].max()
        auth_mode = group["AUTHMODE"].iloc[0] if "AUTHMODE" in group.columns else "UNKNOWN"
        source_file = group["SOURCE FILE"].iloc[0] if "SOURCE FILE" in group.columns else ""
        aggregated_records.append({
            "MAC": mac,
            "SSID": ssid,
            "AUTHMODE": auth_mode,
            "BEST_LAT": best_lat,
            "BEST_LON": best_lon,
            "FIRST_SEEN": first_seen,
            "LAST_SEEN": last_seen,
            "SOURCE_FILE": source_file,
            "CLASSIFICATION": "STATIC"
        })

aggregated_df = pd.DataFrame(aggregated_records)
print(f"Aggregated static signals into {len(aggregated_df)} groups based on 200m threshold.")

# Step 5: Save the aggregated output.
today_str = datetime.today().strftime("%Y%m%d")
output_filename = f"STATIC_SIGNALS-{today_str}.csv"
output_path_outputs = os.path.join(OUTPUTS_DIR, output_filename)
output_path_merges = os.path.join(MERGES_DIR, output_filename)

aggregated_df.to_csv(output_path_outputs, index=False)
aggregated_df.to_csv(output_path_merges, index=False)
print(f"Aggregated static signals saved to:\n  {output_path_outputs}\n  {output_path_merges}")
