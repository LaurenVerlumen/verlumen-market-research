#!/bin/bash
echo "Starting Verlumen Market Research Tool..."
cd "$(dirname "$0")"
source venv/bin/activate
python app.py
