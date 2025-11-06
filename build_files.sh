#!/bin/bash

echo "Starting build process for Teba..."

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "Creating directories..."
mkdir -p staticfiles
mkdir -p media

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Run database migrations (if possible)
echo "Running database migrations..."
python manage.py migrate --noinput || echo "Migrations failed, but continuing build..."

echo "Teba build completed successfully!"