#!/bin/sh
# Linux / macOS: run it with   sh start.sh
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it first (3.10 or newer), for example on Ubuntu/Debian:"
  echo "  sudo apt install python3 python3-venv python3-pip"
  exit 1
fi

# The libraries go in their own folder (.venv): newer Linux refuses "pip install" system-wide.
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || {
    echo "Could not create the .venv folder. On Ubuntu/Debian run:  sudo apt install python3-venv"
    rm -rf .venv
    exit 1
  }
fi
.venv/bin/python -m pip install -q -r requirements.txt || echo "(could not check the libraries, continuing with what is installed)"
.venv/bin/python -c "import gradio, fitz, httpx, ebooklib" 2>/dev/null || {
  echo "The libraries are not installed. Check your internet connection and run this again."
  exit 1
}

export HOST=0.0.0.0 OPEN_BROWSER=1
exec .venv/bin/python app.py
