@echo off
REM Builds VerdantChess.exe (a single double-clickable app) - run this on a Windows PC.
python -m pip install --upgrade pip
python -m pip install chess pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name VerdantChess chess_app.py
echo.
echo Done!  Your app is in the "dist" folder: dist\VerdantChess.exe
pause
