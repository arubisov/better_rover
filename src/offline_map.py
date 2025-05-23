import html
import os
import re
import webbrowser
from datetime import datetime
from typing import List, Optional, Tuple

import folium
import numpy as np
import pandas as pd
from folium import FeatureGroup, LayerControl, plugins
from folium.plugins import MarkerCluster


class Map:
    """
    Coordinate visualization using Folium with offline capability.

    Offline mode uses cacheable tile layers for offline operation.
    """

    POINT_CLUSTERING_THRESHOLD = 50  # cluster points within 50m of each other

    def __init__(self, offline_mode: bool = True):
        """
        Args:
            offline_mode: If True, uses OpenStreetMap tiles that can be cached
        """
        self.offline_mode = offline_mode
        self.map_obj = None
        self.coordinates_df = None
        self.default_zoom = 10
        self.marker_styles = self._init_marker_styles()

    def _init_marker_styles(self) -> dict:
        """Initialize marker styles."""
        return {
            "default": {"color": "red", "icon": "info-sign"},
            "neutral": {"color": "gray", "icon": "question-sign"},
        }

    def load_coordinates(
        self,
        df: pd.DataFrame,
        lat_col: str = "lat",
        lon_col: str = "lon",
        type_col: Optional[str] = None,
    ) -> None:
        """
        Load coordinates from a pandas DataFrame.

        Args:
            df: DataFrame containing coordinate data
            lat_col: Column name for latitude
            lon_col: Column name for longitude
            type_col: Optional column name for marker types
        """
        required_cols = [lat_col, lon_col]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # standardize column names
        self.coordinates_df = df.copy()
        self.coordinates_df = self.coordinates_df.rename(
            columns={
                lat_col: "lat",
                lon_col: "lon",
            }
        )

        if type_col and type_col in df.columns:
            self.coordinates_df["marker_type"] = df[type_col]
        else:
            self.coordinates_df["marker_type"] = "default"

        self._validate_coordinates()

    def _validate_coordinates(self) -> None:
        """Validate latitude and longitude values."""
        # Check for valid lat/lon ranges
        invalid_lat = (self.coordinates_df["lat"] < -90) | (self.coordinates_df["lat"] > 90)
        invalid_lon = (self.coordinates_df["lon"] < -180) | (self.coordinates_df["lon"] > 180)

        if invalid_lat.any():
            print(f"Warning: {invalid_lat.sum()} invalid latitude values found - removing rows")

        if invalid_lon.any():
            print(f"Warning: {invalid_lon.sum()} invalid longitude values found - removing rows")

        # Remove invalid coordinates
        valid_coords = ~(invalid_lat | invalid_lon)
        self.coordinates_df = self.coordinates_df[valid_coords]

    def calculate_map_center(self) -> Tuple[float, float]:
        """Calculate the center point of all coordinates."""
        if self.coordinates_df is None or len(self.coordinates_df) == 0:
            return (0.0, 0.0)

        center_lat = self.coordinates_df["lat"].mean()
        center_lon = self.coordinates_df["lon"].mean()

        return (center_lat, center_lon)

    def calculate_zoom_level(self) -> int:
        """Calculate appropriate zoom level based on coordinate spread."""
        if self.coordinates_df is None or len(self.coordinates_df) < 2:
            return self.default_zoom

        lat_range = self.coordinates_df["lat"].max() - self.coordinates_df["lat"].min()
        lon_range = self.coordinates_df["lon"].max() - self.coordinates_df["lon"].min()

        max_range = max(lat_range, lon_range)

        # Simple zoom calculation - adjust as needed
        if max_range > 10:
            return 5
        elif max_range > 5:
            return 7
        elif max_range > 1:
            return 9
        elif max_range > 0.5:
            return 11
        else:
            return 13

    def create_map(
        self,
        center: Optional[Tuple[float, float]] = None,
        zoom: Optional[int] = None,
        cluster_markers: bool = True,
    ) -> None:
        """
        Create the base map with appropriate settings.

        Args:
            center: Map center as (lat, lon). If None, calculated from data
            zoom: Zoom level. If None, calculated from data spread
            cluster_markers: If True, group nearby markers into clusters
        """
        if center is None:
            center = self.calculate_map_center()

        if zoom is None:
            zoom = self.calculate_zoom_level()

        if self.offline_mode:
            # OpenStreetMap can be cached for offline use
            self.map_obj = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap")
        else:
            self.map_obj = folium.Map(location=center, zoom_start=zoom, tiles="Esri World Imagery")
            # or use ArcGIS:
            # arcgis_tiles = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

        # add terrain
        folium.TileLayer(
            tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            name="CartoDB Voyager",
            overlay=False,
            control=True,
        ).add_to(self.map_obj)

        self.add_markers(cluster_markers=cluster_markers)

        folium.LayerControl().add_to(self.map_obj)  # allow toggle layers
        plugins.MeasureControl().add_to(self.map_obj)  # scale bar
        self.map_obj.add_child(folium.LatLngPopup())  # coordinate display

    def add_markers(self, cluster_markers: bool) -> None:
        """
        Add markers to the map based on loaded coordinates.

        Args:
            cluster_markers: If True, group nearby markers into clusters
        """
        if self.map_obj is None:
            raise ValueError("Map not created. Call create_map() first.")

        if self.coordinates_df is None or len(self.coordinates_df) == 0:
            raise ValueError("No coordinates loaded. Call load_coordinates() first.")

        if "classification" not in self.coordinates_df.columns:
            raise ValueError(
                "DataFrame must contain 'classification' column with values: co-traveler, static, or unknown"
            )

        # create a separate FeatureGroups for each type of class
        cotraveler_group = folium.FeatureGroup(name="Co-travelers (Tracks)")
        static_group = folium.FeatureGroup(name="Static Points")
        unknown_group = folium.FeatureGroup(name="Unknown Points")

        # Optional clustering for static and unknown markers
        if cluster_markers:
            static_cluster = plugins.MarkerCluster(name="Static Markers")
            unknown_cluster = plugins.MarkerCluster(name="Unknown Markers")
            static_group.add_child(static_cluster)
            unknown_group.add_child(unknown_cluster)
            static_parent = static_cluster
            unknown_parent = unknown_cluster
        else:
            static_parent = static_group
            unknown_parent = unknown_group

        for idx, row in self.coordinates_df.iterrows():
            cls = row["classification"].lower()
            popup_content = self._create_popup_content(row, idx)

            if cls == "co-traveler":
                self._add_cotraveler_track(row, idx, cotraveler_group, popup_content)
            elif cls == "static":
                self._add_static_marker(row, idx, static_parent, popup_content)
            elif cls == "unknown":
                self._add_unknown_marker(row, idx, unknown_parent, popup_content)
            else:
                print(
                    f"Warning: Unknown classification '{cls}' for row {idx}. Treating as 'unknown'."
                )
                self._add_unknown_marker(row, idx, unknown_parent, popup_content)

        # Add FeatureGroups to map
        cotraveler_group.add_to(self.map_obj)
        static_group.add_to(self.map_obj)
        unknown_group.add_to(self.map_obj)

    def _add_cotraveler_track(
        self, row: pd.Series, idx: int, group: folium.FeatureGroup, popup_content: str
    ) -> None:
        """Add a polyline track for co-traveler classification."""
        if "coords" not in row or not row["coords"]:
            print(f"Warning: Co-traveler row {idx} missing 'coords' data. Skipping.")
            return

        try:
            # Ensure coords is a list of tuples/lists
            coords = row["coords"]
            if not isinstance(coords, (list, tuple)) or len(coords) == 0:
                print(f"Warning: Invalid coords format for co-traveler row {idx}. Skipping.")
                return

            # Convert coordinates to [lat, lon] format for Folium
            track_coords = []
            for coord in coords:
                if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                    track_coords.append([coord[0], coord[1]])  # [lat, lon]
                else:
                    print(f"Warning: Invalid coordinate {coord} in row {idx}")

            marker_color = self._get_dist_bin_color(row["max_dist"])
            label = f"Co-traveler {self._escape_for_js(row['ssid'])}"

            if len(track_coords) < 2:
                print(
                    f"Warning: Co-traveler track {idx} has fewer than 2 valid coordinates. Creating marker instead."
                )
                # Fall back to marker if insufficient track points
                if track_coords:
                    folium.Marker(
                        location=track_coords[0],
                        popup=folium.Popup(popup_content, max_width=300),
                        tooltip=label,
                        icon=folium.Icon(color=marker_color, icon="road", prefix="glyphicon"),
                    ).add_to(group)
                return

            # Create polyline for the track
            folium.PolyLine(
                locations=track_coords,
                color=marker_color,
                weight=4,
                opacity=0.8,
                popup=folium.Popup(popup_content, max_width=300),
                tooltip=label,
            ).add_to(group)

            # Add start and end markers
            start_marker = folium.Marker(
                location=track_coords[0],
                popup=folium.Popup(f"<b>TRACK START</b><br>{popup_content}", max_width=300),
                tooltip=f"Start: {label}",
                icon=folium.Icon(color="green", icon="play", prefix="glyphicon"),
            )
            start_marker.add_to(group)

            end_marker = folium.Marker(
                location=track_coords[-1],
                popup=folium.Popup(f"<b>TRACK END</b><br>{popup_content}", max_width=300),
                tooltip=f"End: {label}",
                icon=folium.Icon(color="red", icon="stop", prefix="glyphicon"),
            )
            end_marker.add_to(group)

        except Exception as e:
            print(f"Error processing co-traveler track {idx}: {str(e)}")

    def _add_static_marker(self, row: pd.Series, idx: int, parent, popup_content: str) -> None:
        """Add a marker for static classification."""
        marker_type = row.get("marker_type", "default")
        style = self.marker_styles.get(marker_type, self.marker_styles["default"])

        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"Static: {self._escape_for_js(row['ssid'])}",
            icon=folium.Icon(color=style["color"], icon=style["icon"], prefix="glyphicon"),
        ).add_to(parent)

    def _add_unknown_marker(self, row: pd.Series, idx: int, parent, popup_content: str) -> None:
        """Add a marker for unknown classification with distinct styling."""
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"Unknown: {self._escape_for_js(row['ssid'])}",
            icon=folium.Icon(color="gray", icon="question-sign", prefix="glyphicon"),
        ).add_to(parent)

    # handle JavaScript octal escape sequences
    @staticmethod
    def _escape_for_js(text):
        if not isinstance(text, str):
            text = str(text)

        # first handle octal escape sequences (JavaScript issue)
        # replace common octal sequences with their actual characters
        octal_replacements = {
            r"\054": ",",
            r"\040": " ",
            r"\041": "!",
            r"\042": '"',
            r"\047": "'",
            r"\134": "\\",
        }

        for octal, char in octal_replacements.items():
            text = text.replace(octal, char)

        # remove any remaining octal sequences (any 3-digits)
        text = re.sub(r"\\[0-7]{3}", "", text)

        return text

    def _create_popup_content(self, row: pd.Series, idx: int) -> str:
        """Create HTML content for marker popups."""
        cls = row.get("classification", "unknown")

        # Base popup content
        popup_html = f"""
        <div style="width: 250px;">
            <b>MAC:</b> {row["mac"].upper()}<br>
            <b>SSID:</b> {row["ssid"].upper() if row["ssid"] != "" else "UNK"}<br>
            <b>FIRST SEEN:</b> {row["first_seen"]}<br>
            <b>LAST SEEN:</b> {row["last_seen"]}<br>
            <b>SOURCE FILE(S):</b> {row["source_files"].upper()}<br>
        """

        # Add track-specific information for co-travelers
        if cls.lower() == "co-traveler" and "coords" in row and row["coords"]:
            try:
                coord_count = len(row["coords"]) if isinstance(row["coords"], (list, tuple)) else 0
                popup_html += f"""
                <b>FURTHEST DETECTION DISTANCE:</b> {round(row["max_dist"] / 1000.0, 1)} km
                <p><strong>Track Points:</strong> {coord_count}</p>
                """
            except:
                popup_html += f"<p><strong>Track Points:</strong> Invalid data</p>"

        elif cls.lower() != "co-traveler":
            popup_html += f"""
            <p><strong>Coordinates:</strong><br>
            Lat: {row["lat"]:.6f}<br>
            Lon: {row["lon"]:.6f}</p>
            """

        popup_html += "</div>"
        return self._escape_for_js(popup_html)

    def save_map(self, filepath: str, open_browser: bool = True) -> str:
        """
        Save the map to an HTML file.

        Args:
            filepath: Output filepath.
            open_browser: If True, opens the map in default browser

        Returns:
            Path to saved HTML file
        """
        if self.map_obj is None:
            raise ValueError("Map not created. Call create_map() first.")

        # Ensure .html extension
        if not filepath.endswith(".html"):
            filepath += ".html"

        # Save map
        self.map_obj.save(filepath)

        # Get absolute path
        abs_path = os.path.abspath(filepath)

        print(f"Map saved to: {abs_path}")

        if open_browser:
            webbrowser.open(f"file://{abs_path}")

        return abs_path

    @staticmethod
    def _get_dist_bin_label(max_dist):
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

    @staticmethod
    def _get_dist_bin_color(max_dist):
        """Discrete color mapping for bins (using folium icon color names)."""
        if max_dist < 5000:
            return "green"
        elif max_dist < 10000:
            return "blue"
        elif max_dist < 15000:
            return "purple"
        elif max_dist < 20000:
            return "orange"
        else:
            return "red"
