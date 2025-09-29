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
echo "$(date): Starting WildWings mission with timestamp $timestamp" | tee -a logs/wildwings.txt

if [ -z "$DISPLAY" ]; then
    export DISPLAY=:99
    Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &
    sleep 1
fi


# Run the Python script with live output to wildwings.txt
python3 controller.py "$output_dir" 2>&1 | tee -a logs/wildwings.log

# Log completion
echo "$(date): WildWings mission completed" | tee -a logs/wildwings.log