# Verdant Chess  v0.1
Offline chess with a chess.com-style green & white board. No internet needed.

## Play right now (any OS with Python 3.9+)
    pip install chess
    python chess_app.py
(Windows: use `py` instead of `python`. Linux may need `sudo apt install python3-tk`.)

## Make a shareable app (no Python needed on the friend's PC)
- Windows: double-click `build_windows.bat`  ->  `dist\VerdantChess.exe`
- macOS / Linux: run `./build_mac_linux.sh`  ->  `dist/VerdantChess`
Apps must be built on the OS they're meant for (a Windows .exe cannot be built on a Mac).
Send the file in `dist/` to anyone on the same OS.

## Controls
Drag a piece or click it then click the destination - Undo, Hint (orange arrow), Flip board, Resign.

## Levels  (rename/tune them in the LEVELS list in chess_app.py)
Beginner < Medium < Intermediate < Advanced < Master < Grandmaster
Higher levels think deeper and take longer; speed depends on your computer.

## Included
`Intermediate_Chess_Manual.pdf` - tactics & strategy guide with diagrams.
