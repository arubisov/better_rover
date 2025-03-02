#!/usr/bin/env python3
"""
targeted_analytics.py

This script implements the "Targeted Analytics" process.
It performs the following steps:
  1. Prompts the user whether to run Targeted Analytics.
     If declined, the script exits.
  2. If confirmed, prompts the user to enter a MAC or SSID for analysis.
     The user is asked to confirm the spelling and allowed to re-enter if needed.
  3. Asks the user whether the provided identifier is a MAC or an SSID.
  4. Searches through all available:
       - Wigled_Merged CSV files,
       - Airodump_Merged CSV files, and
       - All JSON files (excluding *.ek.json) in Processing/Kismet (searched recursively)
     for records matching the entered value.
  5. Extracts and normalizes fields into a common tabular format with the following headers:
       MAC, SSID, Time, Type, Security, RSSI, Latitude, Longitude, Device Name,
       Manufacturer, Number of Probed SSID, Probed BSSID, Probed SSID, Source File
     Note that not all sources contain every field.
  6. Sorts the records by Time (latest first) and writes the output CSV file to the Outputs directory.
     The output file is named "TA-<name>--<date>.csv" (with any ':' characters in a MAC replaced by '-').

After processing, the user is prompted to run another analysis if desired.
Usage: Run this script after static_signals_map.py and before maintenance tasks.
"""

import os
import sys
import glob
import json
import pandas as pd
from datetime import datetime

# Helper: safely retrieve nested dictionary values using a dotted key.
def get_nested(data, dotted_key, default=""):
    keys = dotted_key.split('.')
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return default
    return data

# Helper: convert unix epoch (sec and usec) to a formatted time string.
def convert_unix_time(sec, usec):
    try:
        ts = float(sec) + float(usec)/1e6
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""

# Set up base directories (assumes this script is run from within the FIDIM folder)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGES_DIR = os.path.join(BASE_DIR, "Processing", "Merges")
OUTPUTS_DIR = os.path.join(BASE_DIR, "Outputs")
KISMET_DIR = os.path.join(BASE_DIR, "Processing", "Kismet")  # JSON files location

def run_targeted_analytics():
    # --- Prompt for Identifier ---
    identifier = input("Enter a MAC or SSID for analysis: ").strip()
    while True:
        correct = input("Is your answer spelled correctly? (y/n): ").strip().lower()
        if correct in ["y", "yes"]:
            break
        else:
            identifier = input("Please re-enter the MAC or SSID: ").strip()
    
    id_type = input("Is the entered value a MAC address or an SSID? (Enter MAC/SSID): ").strip().lower()
    if id_type not in ["mac", "ssid"]:
        print("Invalid entry type. Please run the script again and specify 'MAC' or 'SSID'.")
        sys.exit(1)
    
    identifier_for_filename = identifier.replace(":", "-") if id_type == "mac" else identifier
    today_str = datetime.today().strftime("%Y%m%d")
    output_filename = f"TA-{identifier_for_filename}--{today_str}.csv"
    output_filepath = os.path.join(OUTPUTS_DIR, output_filename)
    
    output_columns = ["MAC", "SSID", "Time", "Type", "Security", "RSSI", "Latitude", "Longitude", 
                      "Device Name", "Manufacturer", "Number of Probed SSID", "Probed BSSID", "Probed SSID", "Source File"]
    
    records = []
    
    # --- Process Wigled_Merged CSV files ---
    wigled_pattern = os.path.join(MERGES_DIR, "Wigled_Merged_*.csv")
    wigled_files = glob.glob(wigled_pattern)
    print(f"Found {len(wigled_files)} Wigled_Merged CSV files.")
    for filepath in wigled_files:
        try:
            df = pd.read_csv(filepath, low_memory=False)
            df.columns = [col.strip() for col in df.columns]
            if "Source File" not in df.columns:
                df["Source File"] = os.path.basename(filepath)
            if id_type == "mac":
                df_filtered = df[df["MAC"].astype(str).str.strip().str.lower() == identifier.lower()]
            else:
                df_filtered = df[df["SSID"].astype(str).str.strip().str.lower() == identifier.lower()]
            for _, row in df_filtered.iterrows():
                record = {
                    "MAC": row.get("MAC", ""),
                    "SSID": row.get("SSID", ""),
                    "Time": row.get("FirstSeen", ""),
                    "Type": "",
                    "Security": row.get("AuthMode", ""),
                    "RSSI": "",
                    "Latitude": row.get("CurrentLatitude", ""),
                    "Longitude": row.get("CurrentLongitude", ""),
                    "Device Name": "",
                    "Manufacturer": "",
                    "Number of Probed SSID": "",
                    "Probed BSSID": "",
                    "Probed SSID": "",
                    "Source File": row.get("Source File", os.path.basename(filepath))
                }
                records.append(record)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
    
    # --- Process Airodump_Merged CSV files ---
    airodump_pattern = os.path.join(MERGES_DIR, "Airodump_Merged_*.csv")
    airodump_files = glob.glob(airodump_pattern)
    print(f"Found {len(airodump_files)} Airodump_Merged CSV files.")
    for filepath in airodump_files:
        try:
            df = pd.read_csv(filepath, low_memory=False)
            df.columns = [col.strip() for col in df.columns]
            if "Source File" not in df.columns:
                df["Source File"] = os.path.basename(filepath)
            if id_type == "mac":
                df_filtered = df[df["BSSID"].astype(str).str.strip().str.lower() == identifier.lower()]
            else:
                df_filtered = df[df["ESSID"].astype(str).str.strip().str.lower() == identifier.lower()]
            for _, row in df_filtered.iterrows():
                record = {
                    "MAC": row.get("BSSID", ""),
                    "SSID": row.get("ESSID", ""),
                    "Time": row.get("LocalTime", ""),
                    "Type": "",
                    "Security": "",
                    "RSSI": row.get("Power", ""),
                    "Latitude": "",
                    "Longitude": "",
                    "Device Name": "",
                    "Manufacturer": "",
                    "Number of Probed SSID": "",
                    "Probed BSSID": "",
                    "Probed SSID": "",
                    "Source File": row.get("Source File", os.path.basename(filepath))
                }
                records.append(record)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
    
    # --- Process JSON files from Processing/Kismet (recursively) ---
    kis_json_pattern = os.path.join(KISMET_DIR, "**", "*.json")
    kis_json_files = glob.glob(kis_json_pattern, recursive=True)
    # Exclude files ending in .ek.json
    kis_json_files = [f for f in kis_json_files if not f.endswith(".ek.json")]
    print(f"Found {len(kis_json_files)} JSON files in Processing/Kismet (excluding .ek.json files).")
    for filepath in kis_json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data = [data]
                for entry in data:
                    # Get the "dot11.device" object.
                    dot11_device = entry.get("dot11.device", {})
                    mac_val = dot11_device.get("dot11.device.last_bssid", "")
                    
                    # Get the advertised SSID map from within the dot11.device object.
                    advertised_map = dot11_device.get("dot11.device.advertised_ssid_map", [])
                    if isinstance(advertised_map, list) and len(advertised_map) > 0:
                        ssid_val = advertised_map[0].get("dot11.advertisedssid.ssid", "")
                        security_val = advertised_map[0].get("dot11.advertisedssid.crypt_string", "")
                        device_name_val = advertised_map[0].get("dot11.advertisedssid.wps_device_name", "")
                    else:
                        ssid_val = entry.get("dot11.advertisedssid.ssid", "")
                        security_val = entry.get("dot11.advertisedssid.crypt_string", "")
                        device_name_val = entry.get("dot11.advertisedssid.wps_device_name", "")
                    
                    # Filter based on the user's identifier.
                    if id_type == "mac":
                        if str(mac_val).strip().lower() != identifier.lower():
                            continue
                    else:
                        if str(ssid_val).strip().lower() != identifier.lower():
                            continue
                    
                    # For time, use kismet.device.base.location.
                    kismet_loc = entry.get("kismet.device.base.location", {})
                    avg_loc = kismet_loc.get("kismet.common.location.avg_loc", {})
                    time_sec = avg_loc.get("kismet.common.location.time_sec", None)
                    time_usec = avg_loc.get("kismet.common.location.time_usec", 0)
                    time_str = convert_unix_time(time_sec, time_usec) if time_sec is not None else ""
                    
                    type_val = entry.get("kismet.device.base.type", "")
                    geopoint = avg_loc.get("kismet.common.location.geopoint", [])
                    lat_val = geopoint[0] if isinstance(geopoint, list) and len(geopoint) >= 2 else ""
                    lon_val = geopoint[1] if isinstance(geopoint, list) and len(geopoint) >= 2 else ""
                    manuf_val = entry.get("kismet.device.base.manuf", "")
                    num_probed = entry.get("dot11.device.num_probed_ssids", "")
                    # Use the same MAC value from dot11.device as Probed BSSID.
                    probed_bssid = dot11_device.get("dot11.device.last_bssid", "")
                    probed_ssid = entry.get("dot11.probedssid.ssid", "")
                    
                    record = {
                        "MAC": mac_val,
                        "SSID": ssid_val,
                        "Time": time_str,
                        "Type": type_val,
                        "Security": security_val,
                        "RSSI": "",
                        "Latitude": lat_val,
                        "Longitude": lon_val,
                        "Device Name": device_name_val,
                        "Manufacturer": manuf_val,
                        "Number of Probed SSID": num_probed,
                        "Probed BSSID": probed_bssid,
                        "Probed SSID": probed_ssid,
                        "Source File": os.path.basename(filepath)
                    }
                    records.append(record)
        except json.JSONDecodeError as je:
            print(f"Error processing {filepath}: {je}")
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
    
    if not records:
        print("No matching records found for the provided identifier.")
        return
    
    result_df = pd.DataFrame(records, columns=output_columns)
    try:
        result_df["Time_sort"] = pd.to_datetime(result_df["Time"], errors="coerce")
    except Exception:
        result_df["Time_sort"] = None
    
    result_df.sort_values(by="Time_sort", ascending=False, inplace=True)
    result_df.drop(columns=["Time_sort"], inplace=True)
    
    try:
        result_df.to_csv(output_filepath, index=False)
        print(f"Targeted Analytics complete. Results saved to {output_filepath}")
    except Exception as e:
        print(f"Error writing output file: {e}")

# --- Main Loop ---
run_initial = input("Would you like to run Targeted Analytics? (y/n): ").strip().lower()
if run_initial not in ["y", "yes"]:
    print("Targeted Analytics process skipped.")
    sys.exit(0)

while True:
    run_targeted_analytics()
    again = input("Would you like to run Targeted Analytics again with a new MAC or SSID? (y/n): ").strip().lower()
    if again not in ["y", "yes"]:
        print("Exiting Targeted Analytics.")
        break
