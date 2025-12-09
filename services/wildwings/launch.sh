#!/bin/bash

# Generate a timestamp
timestamp=$(date +"%Y%m%d_%H%M%S")

# Create main mission directory if it doesn't exist
mkdir -p "mission"

# Create timestamped output directory
output_dir="mission/mission_record_$timestamp"
mkdir -p "$output_dir"

# Ensure logs directory exists
mkdir -p "logs"

# Log start of mission
echo "$(date): Starting WildWings mission with timestamp $timestamp" | tee -a logs/wildwings.log

if [ -z "$DISPLAY" ]; then
    export DISPLAY=:99
    Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &
    sleep 1
fi


# Run the Python script with live output to wildwings.log
# Pass MISSION_LAT and MISSION_LON as arguments if they are set
if [ -n "$MISSION_LAT" ] && [ -n "$MISSION_LON" ]; then
    echo "$(date): Running mission with coordinates: lat=$MISSION_LAT, lon=$MISSION_LON" | tee -a logs/wildwings.log
    python3 controller.py "$output_dir" "$MISSION_LAT" "$MISSION_LON" 2>&1 | tee -a logs/wildwings.log
else
    python3 controller.py "$output_dir" 2>&1 | tee -a logs/wildwings.log
fi

# Capture the exit code from python script
EXIT_CODE=${PIPESTATUS[0]}

# Log completion with exit code
if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): WildWings mission completed successfully" | tee -a logs/wildwings.log
else
    echo "$(date): WildWings mission failed with exit code $EXIT_CODE" | tee -a logs/wildwings.log
    exit $EXIT_CODE
fi