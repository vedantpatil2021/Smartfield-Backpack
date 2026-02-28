#!/bin/bash

echo "Cleaning all files in logs/ folder..."

if [ -d "logs" ]; then
    for file in logs/*; do
        if [ -f "$file" ]; then
            > "$file"
            echo "✓ Cleared: $file"
        fi
    done
    echo "All log files cleared successfully!"
else
    echo "logs/ directory not found"
fi