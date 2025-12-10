#!/bin/bash

WATCH_DIR=$1
SCRIPT=$2
INTERVAL=30

while true; do
    echo "Running Riven sync..."
    $SCRIPT "$WATCH_DIR"
    sleep "$INTERVAL"
done