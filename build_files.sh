#!/bin/bash

echo "Starting Teba build process..."

# Install dependencies (ignore pip warnings)
pip install -r requirements.txt

# Create directories
mkdir -p staticfiles
mkdir -p media

# Try to collect static files, but don't fail the build if it errors
python manage.py collectstatic --noinput --clear || echo "Static collection failed, continuing build..."

echo "Teba build completed!"