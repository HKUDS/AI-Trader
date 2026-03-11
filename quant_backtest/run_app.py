#!/usr/bin/env python3
"""
Quant Backtest - Application Launcher

Run the web interface:
    python run_app.py

Or with streamlit directly:
    streamlit run quant_backtest/ui/app.py
"""

import subprocess
import sys
from pathlib import Path


def check_dependencies():
    """Check if required packages are installed."""
    required = ["streamlit", "plotly"]
    missing = []

    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print("\nInstall with:")
        print(f"  pip install {' '.join(missing)}")
        print("\nOr install all requirements:")
        print("  pip install -r quant_backtest/requirements.txt")
        return False

    return True


def main():
    """Launch the Streamlit application."""
    if not check_dependencies():
        sys.exit(1)

    # Get path to app.py
    app_path = Path(__file__).parent / "ui" / "app.py"

    if not app_path.exists():
        print(f"Error: Could not find {app_path}")
        sys.exit(1)

    print("🚀 Starting Quant Backtest...")
    print("   Open your browser to http://localhost:8501")
    print("   Press Ctrl+C to stop\n")

    # Launch streamlit
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        "--server.headless", "true",
    ])


if __name__ == "__main__":
    main()
