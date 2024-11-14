#!/bin/bash

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Create a new virtual environment
uv venv

# Activate the virtual environment
source .venv/bin/activate

# Install dependencies using uv pip
uv pip install -r requirements.txt

# Install shared package in editable mode
uv pip install -e shared/

echo "UV environment setup complete!"