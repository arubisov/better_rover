# BR-Lite
Better Rover - Lite is an analysis tool meant to assist in processing large volumes of 802.11 survey data to identify potential co-traveling signals as well as likely static access points and their best guess location. It is being developed on a Raspberry Pi 4 running Raspberry Pi OS Lite (64-Bit) and meant to be run on similarly powered devices.

Intended use: BR-Lite is intended to take raw .kismet and .log.csv files from Kismet and Airodump-NG respectively and iteratively parse data to identify Co Traveling signals and provide summary data for Static Signals, while retaining references to raw data inputs for more specialized analytical uses. It is meant to do this in a lightweight format, requiring only a series of editable scripts, python, a.html viewer, and the ability to reference two online databases (ArcGIS ESRI World Imagery maptiles and the IEEE OUI database) for improved visualization. 


Methodology: BRL is run by executing a master script (brl.sh) from the FIDIM directory which controls the phasing of several sub-processes to iteratively convert, merge, parse, and process data. Users are prompted through the analysis iterations to generate tabular and .hmtl interactive maps to display resulting analysis.
