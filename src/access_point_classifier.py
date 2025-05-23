#!/usr/bin/env python3
"""
co_traveler_analysis.py
This script analyzes the merged data produced by the merge process and:
  1. Prompts the user for a date range (in DD-MM-YYYY format) to filter the data. If the user declines,
     all available merged files (from BR-Lite/Processing/Merges) are analyzed.
  2. Loads all qualifying merged CSV files into a DataFrame and standardizes the columns in a case‑insensitive
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

import math
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Self, Set, Tuple

import numpy as np
import pandas as pd

from offline_map import Map


class AccessPointClassifier:
    # distances in meters
    COTRAVELER_DIST_THRESHOLD = 1000
    STATIC_AP_DIST_THRESHOLD = 300

    def __init__(
        self,
        merged_dir: Path,
        outputs_dir: Path,
        whitelist_path: Path = None,
        start_date: str = None,
        end_date: str = None,
    ):
        self.merged_dir = merged_dir
        self.outputs_dir = outputs_dir
        self.whitelist = self._load_whitelist(whitelist_path)
        self.start_dt = self._parse_date(start_date, start_of_day=True) if start_date else None
        self.end_dt = self._parse_date(end_date, start_of_day=False) if end_date else None
        self.df = pd.DataFrame()

    def run(self):
        (
            self.load_files()
            .standardize_columns()
            .clean_data()
            .apply_whitelist()
            .classify()
            .save_csv()
            .build_map()
        )
        print("co-traveler Analysis complete.")
        return 0

    def _load_whitelist(self, path) -> Set[str]:
        """Returns a set of device names and MAC addresses drawn from the whitelist.csv"""
        if not path or not path.exists():
            print(
                "whitelist.csv not found in the base directory; proceeding without whitelist filtering."
            )
            return set()

        df = pd.read_csv(path)
        cols = ["Device Name", "Wifi MAC Address"]
        if not all(col in df.columns for col in cols):
            print(
                "whitelist.csv does not contain correct columns; proceeding without whitelist filtering."
            )
            return set()

        items = set()
        for col in df.columns:
            items |= set(df[col].dropna().astype(str).str.lower().str.strip())
        return items

    def load_files(self) -> Self:
        """
        Step 2: Loads all merged WiGLE CSVs into a single DataFrame
        """

        files = sorted(self.merged_dir.glob("wigle_*.csv"))

        if not files:
            print(f"No merged WiGLE CSV files found in {self.merged_dir}. Exiting.")
            sys.exit(1)
        if self.start_dt and self.end_dt:
            filtered_files = []
            for f in files:
                m = re.search(r"(\d{2}-\d{2}-\d{4})", f.name)
                if (
                    m
                    and self.start_dt.date()
                    <= datetime.strptime(m.group(1), "%d-%m-%Y").date()
                    <= self.end_dt.date()
                ):
                    filtered_files.append(f)
            if not filtered_files:
                print("No merged WiGLE CSV files found for the specified date range. Exiting.")
                sys.exit(1)
            files = filtered_files

        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_csv(f, low_memory=False))
            except Exception as e:
                print(f"Error reading {f}: {e}")
        self.df = pd.concat(dfs, ignore_index=True)
        if not len(self.df):
            print("No data loaded from merged CSV files. Exiting.")
            sys.exit(1)
        print(f"Loaded {len(self.df)} records from {len(files)} merged WiGLE file(s).")
        return self

    def standardize_columns(self) -> Self:
        """
        Step 3: Standardize columns (case-insensitive).
        - Renames columns to a canonical spelling
        - Removes unused columns
        - Ensures expected columns are all present
        """
        df = self.df
        df.columns = [col.strip().lower() for col in df.columns]
        rename_map = {}
        if "firstseen" in df.columns and "time" not in df.columns:
            rename_map["firstseen"] = "time"
        if "currentlatitude" in df.columns and "latitude" not in df.columns:
            rename_map["currentlatitude"] = "latitude"
        if "currentlongitude" in df.columns and "longitude" not in df.columns:
            rename_map["currentlongitude"] = "longitude"
        df.rename(columns=rename_map, inplace=True)
        drop_cols = [
            col
            for col in df.columns
            if col in ["altitudemeters", "accuracymeters", "accuracy meters"]
        ]
        df.drop(columns=drop_cols, inplace=True)
        expected_cols = [
            "mac",
            "ssid",
            "authmode",
            "time",
            "channel",
            "rssi",
            "latitude",
            "longitude",
            "type",
            "source file",
        ]
        for col in expected_cols:
            if col not in df.columns:
                print(
                    f"Expected column '{col}' not found in CSV. Detected columns: {df.columns.tolist()}"
                )
                sys.exit(1)
        self.df = df
        return self

    def clean_data(self) -> Self:
        """
        Step 4: Data cleaning and validation
        - Drops rows with impossible values (lat=0, lon=0)
        - Keep only rows where the date falls within the analysis window
        """
        df = self.df
        df["time_dt"] = pd.to_datetime(df["time"], errors="coerce")
        df = df[(df["latitude"] != 0) & (df["longitude"] != 0)]
        if self.start_dt and self.end_dt:
            df = df[(df["time_dt"] >= self.start_dt) & (df["time_dt"] <= self.end_dt)]
            if df.empty:
                print("No data in date range after filtering. Exiting.")
                sys.exit(1)
        self.df = df
        return self

    def apply_whitelist(self) -> Self:
        """
        Step 5: Filter out whitelisted MACs and SSIDs.
        """
        if not self.whitelist:
            return self

        df = self.df
        initial_len = len(df)
        # filter out any records where the 'mac' or 'ssid' (converted to lowercase) is in the whitelist.
        mask = ~(
            df["mac"].str.lower().isin(self.whitelist)
            | df["ssid"].str.lower().isin(self.whitelist)
        )
        self.df = df[mask]
        print(f"Whitelisted {initial_len - len(df)} records.")
        return self

    def classify(self) -> Self:
        """
        Step 6: For each access point (group by MAC & SSID), categorize the AP as either a
        co-traveler AP, a static AP, or unknown. Get the best guess lat/lon coordinates for each
        AP.
        """
        df = self.df
        df["ssid_filled"] = df["ssid"].replace("", "unk")
        classified, self.cotravelers, self.static_aps = [], {}, {}

        for (mac, ssid), g in df.groupby(["mac", "ssid_filled"]):
            records = g.copy()
            coords = list(zip(records["latitude"], records["longitude"]))

            # defaults
            cls = "unknown"
            max_dist = None
            lat, lon = self._compute_static_ap_coords(records)

            if len(coords) > 1:
                for i in range(len(coords)):
                    for j in range(i + 1, len(coords)):
                        dist = self._haversine(*coords[i], *coords[j])
                        if max_dist is None or dist > max_dist:
                            max_dist = dist

            if max_dist:
                if max_dist >= self.COTRAVELER_DIST_THRESHOLD:
                    cls = "co-traveler"
                    lat, lon = "", ""
                elif max_dist <= self.STATIC_AP_DIST_THRESHOLD:
                    cls = "static"

            classified.append(
                {
                    "mac": mac,
                    "ssid": ssid,
                    "classification": cls,
                    "first_seen": records["time_dt"].min(),
                    "last_seen": records["time_dt"].max(),
                    "lat": lat,
                    "lon": lon,
                    "max_dist": max_dist,
                    "coords": coords,
                    "source_files": ", ".join(sorted(set(records["source file"]))),
                }
            )

        self.classified_df = pd.DataFrame(classified)
        return self

    def save_csv(self) -> Self:
        """
        Step 7. Save categorized access points to CSV.
        """
        output_path = os.path.join(self.outputs_dir, "categorized_access_points.csv")
        self.classified_df.to_csv(output_path, index=False)
        print(f"Categorized signals saved to {output_path}")
        return self

    def build_map(self):
        """
        Step 8: Generate interactive HTML map for co-traveler groups.
        """
        viz = Map(offline_mode=True)
        viz.load_coordinates(self.classified_df, type_col="type")
        viz.create_map(cluster_markers=True)

        output_path = os.path.join(self.outputs_dir, "cotraveler_map.html")
        viz.save_map(output_path)
        return self

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        """Compute the great-circle distance (in meters) between two points."""
        R = 6371000  # meters
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def _parse_date(date_str: str, start_of_day: bool = True):
        try:
            dt = datetime.strptime(date_str, "%d-%m-%Y")
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
            sys.exit(1)
        return (
            dt.replace(hour=0, minute=0, second=0)
            if start_of_day
            else dt.replace(hour=23, minute=59, second=59)
        )

    @staticmethod
    def _compute_static_ap_coords(group: pd.DataFrame) -> Tuple[float, float]:
        """
        Compute best-guess GPS coordinates for an AP classified as "static" by taking the
        weighted average of its (lat,lon) coordinates weighted by the RSSI (Received Signal
        Strength Indicator). RSSI generally ranges from -90 dBm (unusable) to -30 dBm (amazing).
        """
        rssi = group["rssi"].fillna(-130)
        weights = np.maximum(0, 130 + rssi)
        total_weight = weights.sum()

        if total_weight:
            lat = (group["latitude"] * weights).sum() / total_weight
            lon = (group["longitude"] * weights).sum() / total_weight
        else:
            lat = group["latitude"].mean()
            lon = group["longitude"].mean()

        return lat, lon


if __name__ == "__main__":
    PROCESSED_MERGED_DIR = "/Users/70336/dev/better_rover/data/processed/merged"
    OUTPUT_DIR = "/Users/70336/dev/better_rover/data/output"
    WHITELIST_FILE = "/Users/70336/dev/better_rover/whitelist.csv"
    anal = AccessPointClassifier(
        merged_dir=Path(PROCESSED_MERGED_DIR),
        outputs_dir=Path(OUTPUT_DIR),
        whitelist_path=Path(WHITELIST_FILE),
        start_date=None,
        end_date=None,
    )

    (
        anal.load_files()
        .standardize_columns()
        .clean_data()
        .apply_whitelist()
        .classify()
        .save_csv()
        .build_map()
    )


#         # -----------------------------
#         # Step 1: Prompt for date range.
#         # -----------------------------
#         use_range = input("Do you wish to specify a date range for co-traveler Analysis? (y/n): ").strip().lower()
#         date_filter = False
#         if use_range == 'y':
#             start_input = input("Enter beginning date (DD-MM-YYYY): ").strip()
#             end_input = input("Enter ending date (DD-MM-YYYY): ").strip()
#             start_dt = self._parse_date(start_input).replace(hour=0, minute=0, second=0)
#             end_dt = self._parse_date(end_input).replace(hour=23, minute=59, second=59)
#             print(f"Date range specified: {start_dt} to {end_dt}")
#             date_filter = True
#         else:
#             print("Analyzing all available data.")
