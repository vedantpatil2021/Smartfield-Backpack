#!/bin/bash

# Initialize Conda for the shell
source ~/miniconda3/etc/profile.d/conda.sh

# Activate the Conda environment
conda activate wildwing

# Generate a timestamp
timestamp=$(date +"%Y%m%d_%H%M%S")

# Create file to save tracking results
output_dir="missions/misson_record_$timestamp"

# Create the output directory if it does not exist
mkdir -p "$output_dir"

# Run the Python script and save the output to a log file
python3 controller.py "$output_dir" > "logs/output_$timestamp.log" 2>&1