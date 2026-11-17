#!/usr/bin/env bash
# Builds a standalone app on macOS or Linux (build on the OS you want to ship for).
set -e
python3 -m pip install --upgrade pip
python3 -m pip install chess pyinstaller
python3 -m PyInstaller --noconfirm --onefile --windowed --name VerdantChess chess_app.py
echo "Done! Your app is in the dist/ folder."
