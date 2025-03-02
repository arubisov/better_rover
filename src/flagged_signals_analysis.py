#!/usr/bin/env python3
"""
Flagged Signals Analysis

This script searches exclusively across Wigled_Merged CSV files (from wigled sources)
located in the Processing/Merges directory. It:
  1) Identifies unique MAC addresses that are detected at locations at least 300m apart,
     flagging them as Potential co-travelers.
  2) Computes a "Confidence" value (0–100%) based on:
       a) Number of detections (more detections increase confidence)
       b) Spatial spread (maximum pairwise distance, normalized over the range 300m to 10000m)
       c) Duration of detection (time range between first and last detection, normalized over 12 hours)
  3) Aggregates metadata such as detection time ranges, source file names, associated SSID,
     destmac, and any field labeled as type.
  4) Outputs the data as a CSV file (sorted with the highest confidence at the top)
     for further human analysis.

Because input data come from multiple source formats, the script normalizes column names
to a common format early in the process.
"""

import os
import sys
import glob
import math
import pandas as pd
from datetime import datetime

def haversine(lat1, lon1, lat2, lon2):
    """Compute the great-circle distance (in meters) between two points."""
    R = 6371000  # Earth's radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def compute_max_distance(df):
    """Compute the maximum pairwise distance (in meters) among all rows in the DataFrame."""
    max_dist = 0
    coords = df[['latitude', 'longitude']].dropna().values
    n = len(coords)
    if n < 2:
        return 0
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
            if d > max_dist:
                max_dist = d
    return max_dist

def main():
    # Set directories (assumes script is located in BR-Lite/FIDIM/)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MERGES_DIR = os.path.join(BASE_DIR, "Processing", "Merges")
    OUTPUT_DIR = os.path.join(BASE_DIR, "Outputs")

    # Restrict processing exclusively to Wigled_Merged CSV files.
    wigled_files = glob.glob(os.path.join(MERGES_DIR, "Wigled_Merged_*.csv"))
    if not wigled_files:
        print("No Wigled_Merged files found for Flagged Signals Analysis. Exiting.")
        sys.exit(1)
        
    # Debug: print list of Wigled_Merged files being processed
    print("Processing the following Wigled_Merged files for analysis:")
    for f in wigled_files:
        print("  " + f)

    # Load and combine data from each file, tagging each row with the source file name.
    df_list = []
    for f in wigled_files:
        try:
            temp_df = pd.read_csv(f, low_memory=False)
            temp_df['source_file'] = os.path.basename(f)
            df_list.append(temp_df)
        except Exception as e:
            print(f"Error reading {f}: {e}")
    if not df_list:
        print("No data loaded from Wigled_Merged files. Exiting.")
        sys.exit(1)
    df = pd.concat(df_list, ignore_index=True)

    # Normalize column names (lowercase and stripped)
    df.columns = [col.strip().lower() for col in df.columns]

    # If the expected 'latitude' and 'longitude' columns don't exist,
    # check for 'currentlatitude' and 'currentlongitude' and rename them.
    if 'latitude' not in df.columns and 'currentlatitude' in df.columns:
        df.rename(columns={'currentlatitude': 'latitude'}, inplace=True)
    if 'longitude' not in df.columns and 'currentlongitude' in df.columns:
        df.rename(columns={'currentlongitude': 'longitude'}, inplace=True)

    # Ensure required columns exist; if not, add them as empty.
    required_cols = ['mac', 'ssid', 'time', 'latitude', 'longitude']
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""
    # Optional columns
    if 'destmac' not in df.columns:
        df['destmac'] = ""
    if 'type' not in df.columns:
        df['type'] = ""
    if 'source file' not in df.columns:
        df['source file'] = df['source_file'] if 'source_file' in df.columns else ""

    # Convert latitude and longitude to numeric and drop invalid rows.
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    df = df.dropna(subset=['latitude', 'longitude'])

    # Convert time to datetime and drop rows where conversion fails.
    df['time_dt'] = pd.to_datetime(df['time'], errors='coerce')
    df = df.dropna(subset=['time_dt'])

    # Group records by unique MAC address.
    grouped = df.groupby('mac')
    results = []

    for mac, group in grouped:
        count = len(group)
        if count < 1:
            continue

        # Determine the detection time range.
        first_seen = group['time_dt'].min()
        last_seen = group['time_dt'].max()
        time_range = (last_seen - first_seen).total_seconds() / 3600.0  # in hours

        # Compute the maximum spatial distance among detections.
        max_distance = compute_max_distance(group)

        # Only flag MAC addresses detected over at least 300m.
        if max_distance < 300:
            continue

        # Aggregate metadata.
        ssids = ", ".join(sorted(set(group['ssid'].dropna().astype(str))))
        destmacs = ", ".join(sorted(set(group['destmac'].dropna().astype(str))))
        types = ", ".join(sorted(set(group['type'].dropna().astype(str))))
        source_files = ", ".join(sorted(set(group['source file'].dropna().astype(str))))

        # Compute a confidence score from 0 to 100.
        # The score is based on:
        #   - Detection count: normalized such that 20 or more detections gives full score.
        #   - Distance spread: normalized over the range (300m to 10000m).
        #   - Time range: normalized over a 12-hour period.
        count_factor = min(count / 20.0, 1.0)
        distance_factor = min(max((max_distance - 300) / 9700.0, 0), 1.0)
        time_factor = min(time_range / 12.0, 1.0)
        confidence = (0.3 * count_factor + 0.4 * distance_factor + 0.3 * time_factor) * 100

        results.append({
            "mac": mac,
            "ssid": ssids,
            "destmac": destmacs,
            "type": types,
            "detections": count,
            "max_distance_m": round(max_distance, 1),
            "time_range_hours": round(time_range, 2),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "confidence": round(confidence, 1),
            "source_files": source_files
        })

    if not results:
        print("No potential co-traveler signals flagged based on the 300m threshold.")
        sys.exit(0)

    # Create a DataFrame from the results and sort by confidence (highest first).
    results_df = pd.DataFrame(results)
    results_df.sort_values(by="confidence", ascending=False, inplace=True)

    # Save the output as a CSV file.
    output_file = os.path.join(OUTPUT_DIR, "FLAGGED_SIGNALS_ANALYSIS.csv")
    results_df.to_csv(output_file, index=False)
    print(f"Flagged Signals Analysis complete. Results saved to {output_file}")

if __name__ == "__main__":
    main()
