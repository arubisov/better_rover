# BR-Lite
Better Rover - Lite is an analysis tool meant to assist in processing large volumes of 802.11 survey data to identify potential co-traveling signals as well as likely static access points and their best guess location. It is being developed on a Raspberry Pi 4 running Raspberry Pi OS Lite (64-Bit) and meant to be run on similarly powered devices.

Intended use: BR-Lite is intended to take raw .kismet and .log.csv files from Kismet and Airodump-NG respectively and iteratively parse data to identify Co Traveling signals and provide summary data for Static Signals, while retaining references to raw data inputs for more specialized analytical uses. It is meant to do this in a lightweight format, requiring only a series of editable scripts, python, a.html viewer, and the ability to reference two online databases (ArcGIS ESRI World Imagery maptiles and the IEEE OUI database) for improved visualization. 


Methodology: BRL is run by executing a master script (brl.sh) which controls the phasing of several sub-processes to iteratively convert, merge, parse, and process data. It comes to the user packaged in the following:

BR-Lite [Base Directory]/FIDIM [executables directory]
Running the master script initiates analysis in a few phases:

Phase 1: Architecture and Permissions (brl.sh and installer.sh)
-In this phase, BRL creates the necessary directories within the BR-Lite Base Directory and a pre-formatted Whitelist.csv (used to omit survey team signals from co-traveler analysis)
-The directories consist of 
    -Inputs [where users drop consistently formatted raw data files from kismet and airodump
    -Outputs [where users retrieve post-analysis products]
    -Processing [where BRL stores intermediate analysis files that it uses like databases for different analytical passes]

Phase 2: Processing (process_source.sh)
-In this phase, BRL takes raw .kismet files (which are kismet specific unified databases) and airodump log files (the most relevant output for broad level analysis) and converts them into usable outputs
      -Kismet Unified Database Files (.kismet) are converted (using kismet_to_<output> tools )into
          -Wigle CSVs (Geo-referenced, Time Stamped, MAC addresses that included meta data such as RSSI, Type (Wifi or Bluetooth, Altitude, and Accuracy) meant for upload to the Wigle Wifi databases
          -JSON files (JavaScript Object Notation)
          -EKJSON (Elastic Search JSONs that are allegedly more compatible with ELK stack)
-Users can elect to skip already processed data in order to allow the an analyst to collect survey data over time and iteratively deploy this script on an increasing data set. 

Phase 3: Analysis (co_traveler_merge.sh; co_traveler_analysis.py; static_aggregate.py; static_signals_map.py)
-This is frankly a messy phase, mostly because of my own poor understanding of what the data inputs, required outputs, and my own coding ability. The
