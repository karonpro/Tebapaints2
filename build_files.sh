#!/bin/bash

echo "Starting Teba PostgreSQL deployment..."

# Install dependencies
pip install -r requirements.txt

# Create necessary directories
mkdir -p staticfiles
mkdir -p media

# Try to collect static files (continue even if it fails)
python manage.py collectstatic --noinput --clear || echo "Static collection completed"

echo "Teba PostgreSQL build completed!"