# Verdant Chess  v0.3
Offline chess with a chess.com-style interface. No internet needed.

## What's new in 0.3
- Whole interface rebuilt to follow the reference screenshots: wood-grain board, player rows with avatar,
  name and clock box, tabbed right panel (New Game / Games / Players), time-control grid with green selection
  outline, level dropdown, big green Start Game button, gear icon for board themes.
- Everything scales with your screen height, so the proportions stay the same on any monitor.
- New Game tab: choose level, colour (White / Black / Random) and time control (Bullet, Blitz, Rapid,
  Casual incl. "No timer"; "More Time Controls" adds 30 sec, 5+3, 5+5, 20 min).
- Games tab: move list, status, Undo (no-timer games only), Hint, Flip, Resign.
- Players tab: your wins / draws / losses against the bots (saved).
- Clock box states: dark = waiting, grey = your move before the first move, white = running, red = under 10 s.

## Run (Python 3.9+)
    pip install chess
    python chess_app.py
(Linux may need `sudo apt install python3-tk`.)

## Make a shareable app
- Windows: double-click `build_windows.bat` -> `dist\VerdantChess.exe`
- macOS / Linux: `./build_mac_linux.sh` -> `dist/VerdantChess`  (build on the OS you ship for)

## Customise
`LEVELS` (bot strength), `TIME_GROUPS` / `TC` (time controls), `THEMES` (board colours; set the 3rd value
to True for wood grain). Settings are stored in `~/.verdant_chess.json`.
Pieces: `tools/make_pieces.py` regenerates `pieces_data.py` (needs cairosvg).
