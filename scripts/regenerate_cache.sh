#!/bin/bash
# Regenerate Frontend Cache
# Run this script after updating trading data to regenerate the pre-computed cache files

set -e  # Exit on error

echo "========================================"
echo "Regenerating Frontend Cache"
echo "========================================"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

# Try to find Python with yaml module
if command -v ~/miniconda3/bin/python3 &> /dev/null && ~/miniconda3/bin/python3 -c "import yaml" &> /dev/null; then
    PYTHON=~/miniconda3/bin/python3
elif command -v python3 &> /dev/null && python3 -c "import yaml" &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null && python -c "import yaml" &> /dev/null; then
    PYTHON=python
else
    echo "Error: Python with PyYAML not found. Please install: pip install pyyaml"
    exit 1
fi

echo "Using Python: $PYTHON"
echo ""

# Run the cache generation script
echo "Running cache generation script..."
$PYTHON scripts/precompute_frontend_cache.py

echo ""
echo "========================================"
echo "Cache regeneration complete!"
echo "========================================"
echo ""
echo "Generated files:"
echo "  - docs/data/us_cache.json"
echo "  - docs/data/cn_cache.json"
echo ""
echo "These files will be automatically used by the frontend for faster loading."
echo "Commit these files to your repository for GitHub Pages deployment."
