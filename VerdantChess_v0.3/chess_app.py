#!/usr/bin/env python3
"""
Verdant Chess 0.3  -  an offline chess game with a green & white, chess.com-style look.

Run:   python chess_app.py          (needs:  pip install chess)
Build: see README.md (PyInstaller -> single double-clickable app)
"""
import json
import os
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont

import chess

try:
    from pieces_data import SPRITES
except ImportError:          # sprites missing -> board falls back to text symbols
    SPRITES = None

APP_NAME = "Verdant Chess"
APP_VERSION = "0.3"

# =============================================================================
#  ENGINE  (alpha-beta search, piece-square evaluation, quiescence search)
# =============================================================================
PV = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
      chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

# Tables are written from White's point of view, rank 8 first.
PAWN_T = [0, 0, 0, 0, 0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50,
          10, 10, 20, 30, 30, 20, 10, 10, 5, 5, 10, 25, 25, 10, 5, 5,
          0, 0, 0, 20, 20, 0, 0, 0, 5, -5, -10, 0, 0, -10, -5, 5,
          5, 10, 10, -20, -20, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0]
KNIGHT_T = [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 0, 0, 0, -20, -40,
            -30, 0, 10, 15, 15, 10, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30,
            -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 10, 15, 15, 10, 5, -30,
            -40, -20, 0, 5, 5, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50]
BISHOP_T = [-20, -10, -10, -10, -10, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10,
            -10, 0, 5, 10, 10, 5, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10,
            -10, 0, 10, 10, 10, 10, 0, -10, -10, 10, 10, 10, 10, 10, 10, -10,
            -10, 5, 0, 0, 0, 0, 5, -10, -20, -10, -10, -10, -10, -10, -10, -20]
ROOK_T = [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, 10, 10, 10, 10, 5,
          -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5, 0, 0, 0, 5, 5, 0, 0, 0]
QUEEN_T = [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10,
           -10, 0, 5, 5, 5, 5, 0, -10, -5, 0, 5, 5, 5, 5, 0, -5,
           0, 0, 5, 5, 5, 5, 0, -5, -10, 5, 5, 5, 5, 5, 0, -10,
           -10, 0, 5, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20]
KING_MG = [-30, -40, -40, -50, -50, -40, -40, -30] * 4 + \
          [-20, -30, -30, -40, -40, -30, -30, -20, -10, -20, -20, -20, -20, -20, -20, -10,
           20, 20, 0, 0, 0, 0, 20, 20, 20, 30, 10, 0, 0, 10, 30, 20]
KING_EG = [-50, -40, -30, -20, -20, -30, -40, -50, -30, -20, -10, 0, 0, -10, -20, -30,
           -30, -10, 20, 30, 30, 20, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30,
           -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 20, 30, 30, 20, -10, -30,
           -30, -30, 0, 0, 0, 0, -30, -30, -50, -30, -30, -30, -30, -30, -30, -50]
PST = {chess.PAWN: PAWN_T, chess.KNIGHT: KNIGHT_T, chess.BISHOP: BISHOP_T,
       chess.ROOK: ROOK_T, chess.QUEEN: QUEEN_T}

MATE, INF = 100000, 10 ** 9


def evaluate(board):
    """Static score in centipawns from the side-to-move's point of view."""
    pieces = board.piece_map()
    non_pawn = sum(PV[p.piece_type] for p in pieces.values()
                   if p.piece_type not in (chess.PAWN, chess.KING))
    endgame = non_pawn <= 2400
    score = 0
    for sq, p in pieces.items():
        idx = sq ^ 56 if p.color else sq
        if p.piece_type == chess.KING:
            pst = (KING_EG if endgame else KING_MG)[idx]
        else:
            pst = PST[p.piece_type][idx]
        v = PV[p.piece_type] + pst
        score += v if p.color else -v
    return score if board.turn else -score


class Timeout(Exception):
    pass


class Engine:
    def __init__(self, depth, think_time, noise=0, blunder=0.0):
        self.depth, self.think_time = depth, think_time
        self.noise, self.blunder = noise, blunder

    # -- helpers ---------------------------------------------------------
    def _tick(self):
        self.nodes += 1
        if self.nodes & 511 == 0 and not self.free and (self.stop.is_set() or time.time() > self.deadline):
            raise Timeout

    @staticmethod
    def _order(board, moves, pv=None):
        def key(m):
            if m == pv:
                return 10 ** 6
            s = 0
            if board.is_capture(m):
                victim = board.piece_type_at(m.to_square) or chess.PAWN
                attacker = board.piece_type_at(m.from_square)
                s = 10000 + 10 * PV[victim] - PV[attacker] // 10
            if m.promotion:
                s += 9000
            return s
        return sorted(moves, key=key, reverse=True)

    def _quiesce(self, board, alpha, beta, qd):
        self._tick()
        stand = evaluate(board)
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
        if qd >= 6:
            return alpha
        for m in self._order(board, list(board.generate_legal_captures())):
            board.push(m)
            s = -self._quiesce(board, -beta, -alpha, qd + 1)
            board.pop()
            if s >= beta:
                return s
            alpha = max(alpha, s)
        return alpha

    def _search(self, board, depth, alpha, beta, ply):
        self._tick()
        if board.halfmove_clock >= 100 or board.is_insufficient_material():
            return 0
        if board.halfmove_clock >= 4 and board.is_repetition(2):
            return 0
        check = board.is_check()
        if check and ply < 10:
            depth += 1
        if depth <= 0:
            return self._quiesce(board, alpha, beta, 0)
        moves = list(board.legal_moves)
        if not moves:
            return -MATE + ply if check else 0
        best = -INF
        for m in self._order(board, moves):
            board.push(m)
            s = -self._search(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            best = max(best, s)
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best

    # -- public ----------------------------------------------------------
    def choose(self, board, stop=None):
        self.stop = stop or threading.Event()
        self.deadline = time.time() + self.think_time
        self.nodes, self.free = 0, False
        board = board.copy()          # a timeout may leave pushed moves behind
        moves = list(board.legal_moves)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]
        if self.blunder and random.random() < self.blunder:
            return random.choice(moves)
        scores, pv = {}, None
        try:
            for d in range(1, self.depth + 1):
                self.free = d == 1
                alpha, cur = -INF, {}
                for m in self._order(board, moves, pv):
                    board.push(m)
                    beta = INF if self.noise else -alpha
                    s = -self._search(board, d - 1, -INF, beta, 1)
                    board.pop()
                    if self.noise:
                        cur[m] = s
                    elif s > alpha:             # only true improvements count
                        cur[m], alpha = s, s
                    else:
                        cur[m] = -INF           # failed low: just an upper bound
                scores = cur
                pv = max(scores, key=scores.get)
                if abs(scores[pv]) > MATE - 50:      # forced mate found
                    break
        except Timeout:
            pass
        if not scores:
            return random.choice(moves)
        return max(scores, key=lambda m: scores[m] + random.gauss(0, self.noise) + random.random())


# Names are yours to change.  depth = how many half-moves it looks ahead.
LEVELS = [
    ("Beginner",    "Plays quickly and often blunders. Great for learning the rules.",
     dict(depth=1, think_time=1, noise=140, blunder=0.25)),
    ("Medium",      "Sees simple tactics but misses deeper ideas.",
     dict(depth=2, think_time=2, noise=45, blunder=0.06)),
    ("Intermediate", "Solid club player. Punishes free pieces, plans 3 moves ahead.",
     dict(depth=3, think_time=4, noise=8)),
    ("Advanced",    "Calculates 4 half-moves with checks and captures.",
     dict(depth=4, think_time=6)),
    ("Master",      "Deep calculation. Needs accurate tactics to beat.",
     dict(depth=5, think_time=10)),
    ("Grandmaster", "Maximum strength. Thinks up to ~20 seconds per move.",
     dict(depth=8, think_time=20)),
]

# =============================================================================
#  GUI  -  layout measured from the reference screenshots (all numbers below are
#  "reference pixels" for a 788 px board; everything is scaled by self.k)
# =============================================================================
import getpass
import itertools
import math

BG, PANEL, TABBAR = "#302e2b", "#262522", "#21201d"
BTN, BTN_EDGE, SEL = "#363532", "#1f1e1c", "#81b64c"
GREEN_FACE, GREEN_EDGE = "#7bb14b", "#5c9546"
TXT, MUTED = "#e8e8e6", "#b5b3b1"
PX, PY, PW = 878, 27, 490                         # right panel origin / width (reference px)
BX, BY, BW = 44, 97, 788                          # board origin / size
SYM = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}
PTS = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
GLYPH = {chess.PAWN: "\u265f\ufe0e", chess.KNIGHT: "\u265e", chess.BISHOP: "\u265d",
         chess.ROOK: "\u265c", chess.QUEEN: "\u265b", chess.KING: "\u265a"}
START_COUNT = {chess.QUEEN: 1, chess.ROOK: 2, chess.BISHOP: 2, chess.KNIGHT: 2, chess.PAWN: 8}

# Board themes: name -> (light, dark, textured?).  Add your own!
THEMES = {
    "Walnut Wood":   ("#cdae7c", "#7e5533", True),
    "Classic Green": ("#eeeed2", "#769656", False),
    "Ocean Blue":    ("#dfe9f2", "#6b8fb6", False),
    "Royal Purple":  ("#ece6f5", "#8c78b8", False),
}
TIME_GROUPS = [
    ("Bullet", "bullet", ["1 min", "1 + 1", "2 + 1"]),
    ("Blitz", "bolt", ["3 min", "3 + 2", "5 min"]),
    ("Rapid", "watch", ["10 min", "10 + 5", "15 + 10"]),
    ("Casual", "sun", ["No timer", "30 min", "60 min"]),
]
MORE_TC = ["30 sec", "5 + 3", "5 + 5", "20 min"]
TC = {"1 min": (60, 0), "1 + 1": (60, 1), "2 + 1": (120, 1), "3 min": (180, 0), "3 + 2": (180, 2),
      "5 min": (300, 0), "10 min": (600, 0), "10 + 5": (600, 5), "15 + 10": (900, 10),
      "30 min": (1800, 0), "60 min": (3600, 0), "30 sec": (30, 0), "5 + 3": (300, 3),
      "5 + 5": (300, 5), "20 min": (1200, 0)}
NO_TIMER = "No timer"
CFG_PATH = os.path.join(os.path.expanduser("~"), ".verdant_chess.json")
DEFAULT_CFG = {"theme": "Walnut Wood", "level": "Intermediate", "color": "White", "tc": "10 min",
               "record": [0, 0, 0]}


def load_cfg():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(CFG_PATH) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if cfg["theme"] not in THEMES:
        cfg["theme"] = DEFAULT_CFG["theme"]
    if cfg["tc"] not in TC and cfg["tc"] != NO_TIMER:
        cfg["tc"] = DEFAULT_CFG["tc"]
    if cfg["level"] not in [l[0] for l in LEVELS]:
        cfg["level"] = DEFAULT_CFG["level"]
    if not (isinstance(cfg["record"], list) and len(cfg["record"]) == 3):
        cfg["record"] = [0, 0, 0]
    return cfg


def save_cfg(cfg):
    try:
        with open(CFG_PATH, "w") as f:
            json.dump(cfg, f)
    except OSError:
        pass


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def fmt_clock(sec):
    sec = max(0.0, sec)
    if sec < 10:
        return "0:%04.1f" % sec
    sec = int(sec)
    if sec >= 3600:
        return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)
    return "%d:%02d" % (sec // 60, sec % 60)


def make_wood(S, base, seed):
    """Procedural wood-grain square (own algorithm): vertical streaks with a gentle wobble."""
    rng = random.Random(seed)

    def noise(n, step):
        pts = [rng.random() for _ in range(int(n / step) + 3)]
        out = []
        for i in range(n):
            t = i / step
            j = int(t)
            f = t - j
            f = f * f * (3 - 2 * f)
            out.append(pts[j] * (1 - f) + pts[j + 1] * f)
        return out
    L = S + 40
    A, B, C = noise(L, 16), noise(L, 5), noise(L, 1.6)
    ph = rng.random() * 6.28
    br, bg, bb = (int(base[i:i + 2], 16) for i in (1, 3, 5))
    rows = []
    for y in range(S):
        sh = 16 + int(2.2 * math.sin(y * 0.035 + ph))
        row = []
        for x in range(S):
            v = 0.5 * A[x + sh] + 0.32 * B[x + sh] + 0.18 * C[x + sh]
            f = 0.84 + 0.32 * v
            row.append("#%02x%02x%02x" % (min(255, int(br * f)), min(255, int(bg * f)), min(255, int(bb * f))))
        rows.append("{" + " ".join(row) + "}")
    img = tk.PhotoImage(width=S, height=S)
    img.put(" ".join(rows))
    return img


class ChessApp:
    def __init__(self, root):
        self.root = root
        root.title("%s %s" % (APP_NAME, APP_VERSION))
        root.configure(bg=BG)
        root.resizable(False, False)
        self.cfg = load_cfg()
        self.theme = self.cfg["theme"]
        sizes = sorted(s for s in (SPRITES or {}) if s >= 48) or [64]
        want = max(48, min(104, (root.winfo_screenheight() - 110) // 10))
        self.S = max([s for s in sizes if s <= want] or [sizes[0]])
        self.k = 8 * self.S / BW
        k = self.k
        fams = set(tkfont.families())
        pick = lambda names, dflt: next((f for f in names if f in fams), dflt)
        self.ui = pick(("Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu", "Inter", "DejaVu Sans"), "TkDefaultFont")
        self.mono = pick(("Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"), "TkFixedFont")
        self.pfont = pick(("Segoe UI Symbol", "Apple Symbols", "DejaVu Sans", "FreeSerif"), "TkDefaultFont")
        self.imgs = self.small = self.icons = {}
        if SPRITES:
            mk = lambda size: {n: tk.PhotoImage(data=d) for n, d in SPRITES[size].items()}
            self.imgs, self.small, self.icons = mk(self.S), mk(24), mk(48)
        self.tex = None
        self.ids = itertools.count()
        self.username = (getpass.getuser() or "Player").replace("_", " ").title()
        self.board = chess.Board()
        self.human, self.flipped = chess.WHITE, False
        self.level_idx = [l[0] for l in LEVELS].index(self.cfg["level"])
        self.tc_label = self.cfg["tc"]
        self.base, self.inc = TC.get(self.tc_label, (None, 0))
        self.clocks = {True: 0.0, False: 0.0}
        self.last_t = None
        self.selected = self.drag_from = self.hint = None
        self.targets, self.sans, self.clock_ids = set(), [], {}
        self.over, self.thinking, self.token = False, False, 0
        self.status_text = ""
        self.tab = "new"
        self.sel = {"level": self.level_idx, "color": self.cfg["color"], "tc": self.cfg["tc"]}
        self.stop_ev = threading.Event()
        self.q = queue.Queue()
        self.cv = tk.Canvas(root, width=int(1395 * k), height=int(986 * k), bg=BG, highlightthickness=0)
        self.cv.pack()
        self.moves = tk.Text(self.cv, bg="#2b2a27", fg=TXT, relief="flat", bd=0, highlightthickness=0,
                             font=(self.mono, -max(9, int(17 * k))), state="disabled", padx=12, pady=8,
                             cursor="arrow", wrap="none")
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.start_game(self.cfg["level"], self.cfg["color"], self.cfg["tc"], ask=False)
        self.draw_panel()
        self._poll()
        self._tick_clock()

    # ============================================================ helpers ==
    def F(self, size, bold=False):
        return (self.ui, -max(8, int(size * self.k)), "bold" if bold else "normal")

    def tx(self, x, y, text, size, fill=TXT, bold=False, anchor="center", tags="panel"):
        return self.cv.create_text(x * self.k, y * self.k, text=text, font=self.F(size, bold), fill=fill,
                                   anchor=anchor, tags=tags)

    def rr(self, x1, y1, x2, y2, r, tags="panel", **kw):
        k, r = self.k, r * self.k
        x1, y1, x2, y2 = x1 * k, y1 * k, x2 * k, y2 * k
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
               x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.cv.create_polygon(pts, smooth=True, tags=tags, **kw)

    def line(self, pts, fill, width, tags="panel", **kw):
        k = self.k
        return self.cv.create_line([v * k for v in pts], fill=fill, width=max(1, width * k), tags=tags,
                                   capstyle="round", joinstyle="round", **kw)

    def oval(self, x1, y1, x2, y2, tags="panel", **kw):
        k = self.k
        return self.cv.create_oval(x1 * k, y1 * k, x2 * k, y2 * k, tags=tags, **kw)

    def poly(self, pts, tags="panel", **kw):
        return self.cv.create_polygon([v * self.k for v in pts], tags=tags, **kw)

    def measure(self, text, size, bold=False):
        return tkfont.Font(family=self.ui, size=-max(8, int(size * self.k)), weight="bold" if bold else "normal").measure(text) / self.k

    def button(self, x1, y1, x2, y2, label, cmd, face=BTN, edge=BTN_EDGE, fg=TXT, size=20, selected=False,
               r=7, bold=False, depth=4, tags="panel"):
        tag = "btn%d" % next(self.ids)
        self.rr(x1, y1, x2, y2, r, (tags, tag), fill=edge, outline="")
        f = self.rr(x1, y1, x2, y2 - depth, r, (tags, tag), fill=face, outline=SEL if selected else "",
                    width=max(1, int(2 * self.k)))
        if label:
            self.tx((x1 + x2) / 2, (y1 + y2 - depth) / 2, label, size, fg, bold, tags=(tags, tag))
        hov = blend(face, "#ffffff", 0.07)
        self.cv.tag_bind(tag, "<Enter>", lambda e: (self.cv.itemconfig(f, fill=hov), self.cv.config(cursor="hand2")))
        self.cv.tag_bind(tag, "<Leave>", lambda e: (self.cv.itemconfig(f, fill=face), self.cv.config(cursor="")))
        self.cv.tag_bind(tag, "<Button-1>", lambda e: cmd())
        return tag

    def clickable(self, tag, cmd):
        self.cv.tag_bind(tag, "<Button-1>", lambda e: cmd())
        self.cv.tag_bind(tag, "<Enter>", lambda e: self.cv.config(cursor="hand2"))
        self.cv.tag_bind(tag, "<Leave>", lambda e: self.cv.config(cursor=""))

    # ------------------------------------------------------------- icons --
    def icon(self, kind, cx, cy, s=24, color=MUTED, tags="panel"):
        h = s / 2
        if kind == "plus":
            self.rr(cx - h, cy - h, cx + h, cy + h, 4, tags, fill=color, outline="")
            self.line([cx - h * .55, cy, cx + h * .55, cy], "#262522", s * .2, tags)
            self.line([cx, cy - h * .55, cx, cy + h * .55], "#262522", s * .2, tags)
        elif kind == "checker":
            c = s / 3
            self.rr(cx - h, cy - h, cx + h, cy + h, 3, tags, fill=color, outline="")
            for i in range(3):
                for j in range(3):
                    if (i + j) % 2 == 0:
                        self.cv.create_rectangle((cx - h + i * c) * self.k, (cy - h + j * c) * self.k,
                                                 (cx - h + (i + 1) * c) * self.k, (cy - h + (j + 1) * c) * self.k,
                                                 fill="#33312e", outline="", tags=tags)
        elif kind == "people":
            for dx, dy, sc in ((-h * .35, -h * .35, .8), (h * .25, -h * .05, 1)):
                self.oval(cx + dx - h * .28 * sc, cy + dy - h * .28 * sc - h * .2, cx + dx + h * .28 * sc,
                          cy + dy + h * .28 * sc - h * .2, tags, fill=color, outline="")
                self.rr(cx + dx - h * .55 * sc, cy + dy + h * .2, cx + dx + h * .55 * sc, cy + dy + h * .75, 5,
                        tags, fill=color, outline="")
        elif kind == "bullet":
            self.line([cx - h * .6, cy + h * .6, cx + h * .35, cy - h * .35], "#f0a21e", s * .38, tags)
            self.line([cx + h * .1, cy - h * .1, cx + h * .62, cy - h * .62], "#ffd36a", s * .2, tags)
        elif kind == "bolt":
            self.poly([cx + h * .2, cy - h, cx - h * .55, cy + h * .15, cx - h * .05, cy + h * .15,
                       cx - h * .25, cy + h, cx + h * .55, cy - h * .2, cx + h * .05, cy - h * .2],
                      tags, fill="#f4c20d", outline="")
        elif kind == "watch":
            self.oval(cx - h * .8, cy - h * .7, cx + h * .8, cy + h * .9, tags, outline="#81b64c",
                      width=max(2, s * .13 * self.k), fill="")
            self.line([cx, cy - h * .95, cx, cy - h * .7], "#81b64c", s * .14, tags)
            self.line([cx, cy + h * .1, cx + h * .35, cy - h * .2], "#81b64c", s * .13, tags)
        elif kind == "sun":
            self.oval(cx - h * .45, cy - h * .45, cx + h * .45, cy + h * .45, tags, fill="#f0a21e", outline="")
            for a in range(8):
                ang = a * math.pi / 4
                self.line([cx + math.cos(ang) * h * .65, cy + math.sin(ang) * h * .65,
                           cx + math.cos(ang) * h * .98, cy + math.sin(ang) * h * .98], "#f0a21e", s * .14, tags)
        elif kind == "chevron":
            self.line([cx - h * .45, cy - h * .2, cx, cy + h * .25, cx + h * .45, cy - h * .2], color, s * .14, tags)
        elif kind == "gear":
            self.cv.create_text(cx * self.k, cy * self.k, text="\u2699", fill=color, font=(self.pfont, -int(s * self.k)), tags=tags)

    # ======================================================= LEFT COLUMN ==
    def sq_xy(self, sq):
        f, r, S = chess.square_file(sq), chess.square_rank(sq), self.S
        x, y = ((7 - f) * S, r * S) if self.flipped else (f * S, (7 - r) * S)
        return BX * self.k + x, BY * self.k + y

    def xy_sq(self, x, y):
        x, y = x - BX * self.k, y - BY * self.k
        col, row = int(x // self.S), int(y // self.S)
        if x < 0 or y < 0 or not (0 <= col < 8 and 0 <= row < 8):
            return None
        f, r = (7 - col, row) if self.flipped else (col, 7 - row)
        return chess.square(f, r)

    def build_textures(self):
        lt, dk, wood = THEMES[self.theme]
        self.tex = {}
        if not wood:
            return
        yel, red = "#f5f522", "#e63946"
        for v in range(4):
            for name, base in (("L", lt), ("D", dk)):
                self.tex[(name, v, "n")] = make_wood(self.S, base, 100 + v * 7 + (name == "D") * 3)
                self.tex[(name, v, "h")] = make_wood(self.S, blend(base, yel, .55), 100 + v * 7 + (name == "D") * 3)
        for name, base in (("L", lt), ("D", dk)):
            self.tex[(name, 0, "c")] = make_wood(self.S, blend(base, red, .65), 100 + (name == "D") * 3)

    def draw_piece(self, piece, cx, cy, tag):
        key = ("w" if piece.color else "b") + SYM[piece.piece_type]
        if self.imgs:
            self.cv.create_image(cx, cy, image=self.imgs[key], tags=tag)
        else:
            fill, edge = ("#ffffff", "#2b2b2b") if piece.color else ("#1d1d1d", "#000000")
            size, g = int(self.S * 0.74), GLYPH[piece.piece_type]
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                self.cv.create_text(cx + dx, cy + dy, text=g, font=(self.pfont, size), fill=edge, tags=tag)
            self.cv.create_text(cx, cy, text=g, font=(self.pfont, size), fill=fill, tags=tag)

    def draw(self):
        c, S, b = self.cv, self.S, self.board
        c.delete("board")
        if self.tex is None:
            self.build_textures()
        lt, dk, wood = THEMES[self.theme]
        last = b.peek() if b.move_stack else None
        check_sq = b.king(b.turn) if b.is_check() else None
        small = (self.ui, -max(9, int(S * 0.165)), "bold")
        for sq in range(64):
            f, r = chess.square_file(sq), chess.square_rank(sq)
            x, y = self.sq_xy(sq)
            light = (f + r) % 2 == 1
            kind = "n"
            if (last and sq in (last.from_square, last.to_square)) or sq == self.selected:
                kind = "h"
            if sq == check_sq:
                kind = "c"
            base = lt if light else dk
            if wood:
                v = 0 if kind == "c" else (f * 7 + r * 3) % 4
                c.create_image(x, y, image=self.tex[("L" if light else "D", v, kind)], anchor="nw", tags="board")
                col = blend(base, "#f5f522", .55) if kind != "n" else base
            else:
                col = base
                if kind == "h":
                    col = blend(base, "#f5f522", .55)
                if kind == "c":
                    col = blend(base, "#e63946", .65)
                c.create_rectangle(x, y, x + S, y + S, fill=col, outline="", tags="board")
            lab = blend(dk, lt, .28) if light else blend(lt, dk, .2)
            if x == BX * self.k + (7 * S if self.flipped else 0):
                c.create_text(x + S * .06, y + S * .05, text=str(r + 1), anchor="nw", font=small, fill=lab, tags="board")
            if y == BY * self.k + (0 if self.flipped else 7 * S):
                c.create_text(x + S * .95, y + S * .96, text="abcdefgh"[f], anchor="se", font=small, fill=lab, tags="board")
            if sq in self.targets:
                dot = blend(col, "#000000", .18)
                if b.piece_at(sq) or b.is_en_passant(chess.Move(self.selected, sq)):
                    c.create_oval(x + 3, y + 3, x + S - 3, y + S - 3, outline=dot, width=max(4, S // 12), tags="board")
                else:
                    r0 = S * 0.17
                    c.create_oval(x + S / 2 - r0, y + S / 2 - r0, x + S / 2 + r0, y + S / 2 + r0, fill=dot, outline="", tags="board")
        for sq, p in b.piece_map().items():
            if sq != self.drag_from:
                x, y = self.sq_xy(sq)
                self.draw_piece(p, x + S / 2, y + S / 2, "board")
        if self.hint:
            x1, y1 = self.sq_xy(self.hint.from_square)
            x2, y2 = self.sq_xy(self.hint.to_square)
            c.create_line(x1 + S / 2, y1 + S / 2, x2 + S / 2, y2 + S / 2, arrow="last", width=S * 0.13, fill="#f0a21e",
                          arrowshape=(S * .3, S * .3, S * .15), tags="board")

    def draw_rows(self):
        """Avatar + name + captured pieces + clock for both players."""
        cv, b, h = self.cv, self.board, self.human
        cv.delete("rows")
        self.clock_ids = {}
        bottom = chess.BLACK if self.flipped else chess.WHITE
        lost = {col: [] for col in (True, False)}
        for col in (True, False):
            for pt, n in START_COUNT.items():
                lost[col] += [pt] * max(0, n - len(b.pieces(pt, col)))
        for col, y in ((not bottom, 27), (bottom, 900)):
            you = col == h
            x = BX
            self.rr(x, y, x + 56, y + 56, 4, "rows", fill="#e7e5e3" if you else "#4b4847", outline="")
            if you:                                                    # light avatar with a pawn
                self.oval(x + 19, y + 9, x + 37, y + 27, "rows", fill="#9a9895", outline="")
                self.poly([x + 22, y + 28, x + 34, y + 28, x + 41, y + 44, x + 15, y + 44], "rows", fill="#9a9895", outline="")
                self.rr(x + 12, y + 44, x + 44, y + 50, 2, "rows", fill="#9a9895", outline="")
            else:                                                      # dark avatar with a silhouette
                self.oval(x + 18, y + 9, x + 38, y + 29, "rows", fill="#262421", outline="")
                self.oval(x + 6, y + 33, x + 50, y + 70, "rows", fill="#262421", outline="")
                self.cv.create_rectangle(x * self.k, (y + 56) * self.k, (x + 57) * self.k, (y + 72) * self.k, fill=BG, outline="", tags="rows")
            name = self.username if you else "%s Bot" % LEVELS[self.level_idx][0]
            self.tx(116, y + 17, name, 18, "#ffffff", True, "w", "rows")
            suffix = " (%s)" % ("White" if col else "Black")
            self.tx(116 + self.measure(name, 18, True), y + 17, suffix, 17, "#9d9b98", False, "w", "rows")
            adv = sum(PTS[p] for p in lost[not col]) - sum(PTS[p] for p in lost[col])
            cx, last = 116, None
            for pt in sorted(lost[not col], key=lambda p: -PTS[p]):
                if last is not None and pt != last:
                    cx += 6
                if self.small:
                    cv.create_image(cx * self.k, (y + 43) * self.k, image=self.small[("w" if not col else "b") + SYM[pt]], anchor="w", tags="rows")
                cx += 13 if pt == chess.PAWN else 19
                last = pt
            if adv > 0:
                self.tx(cx + 6, y + 43, "+%d" % adv, 14, "#9d9b98", True, "w", "rows")
            rect = self.rr(BX + BW - 197, y, BX + BW, y + 56, 4, "rows", fill="#2b2925", outline="")
            txt = self.tx(BX + BW - 16, y + 28, "", 36, "#6e6d6a", True, "e", "rows")
            self.clock_ids[col] = (rect, txt)
        gear = self.cv.create_text(855 * self.k, 55 * self.k, text="\u2699", fill="#8b8987", font=(self.pfont, -int(30 * self.k)), tags=("rows", "gear"))
        self.clickable("gear", self.open_themes)
        self.update_clocks()

    # ======================================================== RIGHT PANEL ==
    def set_tab(self, t):
        self.tab = t
        self.draw_panel()

    def draw_panel(self):
        cv = self.cv
        cv.delete("panel")
        self.cv.itemconfigure("moves", state="normal")
        for w in cv.find_withtag("movewin"):
            cv.delete(w)
        a = lambda v: PX + v
        b_ = lambda v: PY + v
        self.rr(PX, PY, PX + PW, PY + 945, 8, fill=PANEL, outline="")
        self.rr(PX, PY, PX + PW, PY + 100, 8, fill=TABBAR, outline="")
        self.cv.create_rectangle(PX * self.k, (PY + 60) * self.k, (PX + PW) * self.k, (PY + 80) * self.k, fill=TABBAR, outline="", tags="panel")
        self.cv.create_rectangle(PX * self.k, (PY + 80) * self.k, (PX + PW) * self.k, (PY + 100) * self.k, fill=PANEL, outline="", tags="panel")
        tw = PW / 3
        for i, (key, label, ic) in enumerate((("new", "New Game", "plus"), ("games", "Games", "checker"), ("players", "Players", "people"))):
            x1 = PX + i * tw
            active = self.tab == key
            tag = "tab_" + key
            if active:
                self.rr(x1, PY, x1 + tw, PY + 100, 8, (("panel", tag)), fill=PANEL, outline="")
                self.cv.create_rectangle(x1 * self.k, (PY + 60) * self.k, (x1 + tw) * self.k, (PY + 80) * self.k, fill=PANEL, outline="", tags=("panel", tag))
            else:
                self.cv.create_rectangle(x1 * self.k, PY * self.k, (x1 + tw) * self.k, (PY + 80) * self.k, fill=TABBAR, outline="", tags=("panel", tag))
            self.icon(ic, x1 + tw / 2, PY + 28, 26, "#ffffff" if active else MUTED, ("panel", tag))
            self.tx(x1 + tw / 2, PY + 58, label, 17, "#ffffff" if active else MUTED, False, "center", ("panel", tag))
            self.clickable(tag, lambda k_=key: self.set_tab(k_))
        {"new": self.page_new, "games": self.page_games, "players": self.page_players}[self.tab]()

    # -- tab 1: New Game --------------------------------------------------
    def page_new(self):
        a = lambda v: PX + v
        y0 = PY
        lv = self.sel["level"]
        # opponent dropdown (the "Standard" selector of the reference)
        tag = self.button(a(42), y0 + 100, a(462), y0 + 184, "", self.open_levels, face="#353432", edge="#2a2927", r=10, depth=4)
        self.icon("checker", a(88), y0 + 138, 34, "#bdbbb9", ("panel", tag))
        self.tx(a(252), y0 + 128, LEVELS[lv][0], 26, "#ffffff", True, "center", ("panel", tag))
        self.tx(a(252), y0 + 158, LEVELS[lv][1].split(". ")[0].rstrip("."), 14, "#9d9b98", False, "center", ("panel", tag))
        self.icon("chevron", a(432), y0 + 138, 22, "#9d9b98", ("panel", tag))
        # play-as row (takes the place of the "Rated" toggle)
        self.tx(a(42), y0 + 223, "Play as", 24, "#f1f1f1", False, "w")
        for i, key in enumerate(("White", "Black", "Random")):
            x1 = a(462) - 3 * 62 - 2 * 8 + i * 70
            t = self.button(x1, y0 + 200, x1 + 62, y0 + 246, "", lambda k_=key: self.pick("color", k_),
                            face="#c9c7c5" if key == "Black" else "#363532", selected=self.sel["color"] == key, depth=3, r=6)
            if key == "Random":
                self.tx(x1 + 31, y0 + 221, "?", 24, "#e8e8e6", True, "center", ("panel", t))
            elif self.small:
                self.cv.create_image((x1 + 31) * self.k, (y0 + 221) * self.k, image=self.small["wP" if key == "White" else "bP"], tags=("panel", t))
        # time grid
        ys = (275, 395, 515, 635)
        for (name, ic, labels), ly in zip(TIME_GROUPS, ys):
            self.icon(ic, a(54), y0 + ly - 1, 24, tags="panel")
            self.tx(a(74), y0 + ly, name, 21, "#f1f1f1", False, "w")
            for i, lab in enumerate(labels):
                x1 = a(42) + i * 143
                self.button(x1, y0 + ly + 25, x1 + 134, y0 + ly + 82, lab, lambda l=lab: self.pick("tc", l),
                            selected=self.sel["tc"] == lab, size=21, bold=False)
        more = self.sel["tc"] if self.sel["tc"] in MORE_TC else None
        mt = self.tx(a(252), y0 + 746, "More Time Controls" if not more else "More: %s selected" % more, 20,
                     SEL if more else MUTED, False, "center")
        w = self.measure("More Time Controls" if not more else "More: %s selected" % more, 20)
        self.icon("chevron", a(252) + w / 2 + 20, y0 + 747, 22, MUTED, "panel")
        hit = self.cv.create_rectangle((a(120)) * self.k, (y0 + 730) * self.k, a(384) * self.k, (y0 + 764) * self.k, outline="", fill="", tags=("panel", "more"))
        self.clickable("more", self.open_more)
        self.button(a(42), y0 + 786, a(462), y0 + 872, "Start Game", self.start_clicked, face=GREEN_FACE, edge=GREEN_EDGE,
                    fg="#ffffff", size=32, bold=True, r=10, depth=6)
        self.tx(a(252), y0 + 913, "6 levels", 17, "#f1f1f1", True, "e")
        self.tx(a(262), y0 + 913, "OFFLINE", 15, "#8b8987", False, "w")

    def pick(self, key, val):
        self.sel[key] = val
        self.draw_panel()

    def open_levels(self):
        m = tk.Menu(self.root, tearoff=0, bg="#353432", fg="#ffffff", activebackground=SEL, activeforeground="#ffffff",
                    font=(self.ui, 12), bd=0)
        for i, l in enumerate(LEVELS):
            m.add_command(label=l[0], command=lambda i=i: self.pick("level", i))
        m.tk_popup(int(self.cv.winfo_rootx() + (PX + 42) * self.k), int(self.cv.winfo_rooty() + (PY + 184) * self.k))

    def open_more(self):
        m = tk.Menu(self.root, tearoff=0, bg="#353432", fg="#ffffff", activebackground=SEL, activeforeground="#ffffff",
                    font=(self.ui, 12), bd=0)
        for lab in MORE_TC:
            m.add_command(label=lab, command=lambda l=lab: self.pick("tc", l))
        m.tk_popup(int(self.cv.winfo_rootx() + (PX + 160) * self.k), int(self.cv.winfo_rooty() + (PY + 764) * self.k))

    def start_clicked(self):
        s = self.sel
        if self.start_game(LEVELS[s["level"]][0], s["color"], s["tc"]):
            self.set_tab("games")

    # -- tab 2: current game ----------------------------------------------
    def page_games(self):
        a = lambda v: PX + v
        info = "%s Bot  \u00b7  %s" % (LEVELS[self.level_idx][0], self.tc_label if self.base else "No timer")
        self.tx(a(42), PY + 128, info, 22, "#ffffff", True, "w")
        self.cv.create_window(a(42) * self.k, (PY + 160) * self.k, window=self.moves, anchor="nw",
                              width=420 * self.k, height=470 * self.k, tags=("panel", "movewin"))
        self.status_id = self.cv.create_text(a(42) * self.k, (PY + 658) * self.k, text=self.status_text, anchor="nw",
                                             width=420 * self.k, font=self.F(19, True), fill="#ffffff", tags=("panel", "status"))
        for i, (lab, cmd) in enumerate((("\u21b6  Undo", self.undo), ("\u2605  Hint", self.get_hint),
                                        ("\u21c5  Flip", self.flip), ("\u2690  Resign", self.resign))):
            x1, y1 = a(42) + (i % 2) * 215, PY + 735 + (i // 2) * 70
            self.button(x1, y1, x1 + 205, y1 + 62, lab, cmd, size=21, bold=True)
        self.update_moves()

    # -- tab 3: players -----------------------------------------------------
    def page_players(self):
        a = lambda v: PX + v
        for i, (name, sub, you) in enumerate(((self.username, "You \u00b7 playing %s" % ("White" if self.human else "Black"), True),
                                              ("%s Bot" % LEVELS[self.level_idx][0], LEVELS[self.level_idx][1], False))):
            y = PY + 110 + i * 120
            self.rr(a(42), y, a(462), y + 100, 10, fill="#2d2c29", outline="")
            self.rr(a(58), y + 22, a(114), y + 78, 4, fill="#e7e5e3" if you else "#4b4847", outline="")
            self.oval(a(77), y + 31, a(95), y + 49, fill="#9a9895" if you else "#262421", outline="")
            self.rr(a(70), y + 53, a(102), y + 70, 6, fill="#9a9895" if you else "#262421", outline="")
            self.tx(a(130), y + 36, name, 21, "#ffffff", True, "w")
            self.tx(a(130), y + 68, sub.split(". ")[0][:44], 14, "#9d9b98", False, "w")
        self.tx(a(42), PY + 380, "Your record against the bots", 21, "#f1f1f1", False, "w")
        w, d, l = self.cfg["record"]
        for i, (val, lab) in enumerate(((w, "Wins"), (d, "Draws"), (l, "Losses"))):
            x1 = a(42) + i * 143
            self.rr(x1, PY + 410, x1 + 134, PY + 520, 8, fill="#2d2c29", outline="")
            self.tx(x1 + 67, PY + 452, str(val), 40, "#ffffff", True)
            self.tx(x1 + 67, PY + 494, lab, 15, "#9d9b98")
        self.button(a(42), PY + 545, a(462), PY + 603, "Reset record", self.reset_record, size=18)

    def reset_record(self):
        self.cfg["record"] = [0, 0, 0]
        save_cfg(self.cfg)
        self.draw_panel()

    def record(self, idx):
        self.cfg["record"][idx] += 1
        save_cfg(self.cfg)
        if self.tab == "players":
            self.draw_panel()

    # ------------------------------------------------------------ updates --
    def update_moves(self):
        t = self.moves
        t.config(state="normal")
        t.delete("1.0", "end")
        for i in range(0, len(self.sans), 2):
            pair = self.sans[i:i + 2]
            t.insert("end", "%3d.  %-9s %s\n" % (i // 2 + 1, pair[0], pair[1] if len(pair) > 1 else ""))
        t.config(state="disabled")
        t.see("end")

    def update_panels(self):
        self.draw_rows()
        if self.tab == "games":
            self.update_moves()
        elif self.tab == "players":
            self.draw_panel()

    def set_status(self, s):
        self.status_text = s
        if self.tab == "games" and self.cv.find_withtag("status"):
            self.cv.itemconfig("status", text=s)

    # ------------------------------------------------------------- clocks --
    def clock_running(self):
        return bool(self.base) and not self.over and len(self.board.move_stack) >= 1

    def _charge(self):
        if self.clock_running():
            now = time.monotonic()
            if self.last_t is not None:
                self.clocks[self.board.turn] -= now - self.last_t
            self.last_t = now
        else:
            self.last_t = None

    def _tick_clock(self):
        self._charge()
        if self.clock_running() and self.clocks[self.board.turn] <= 0:
            self.flag(self.board.turn)
        self.update_clocks()
        self.root.after(100, self._tick_clock)

    def update_clocks(self):
        for col, (rect, txt) in self.clock_ids.items():
            if not self.base:
                self.cv.itemconfig(rect, fill="#2b2925")
                self.cv.itemconfig(txt, text="\u221e", fill="#6e6d6a")
                continue
            sec = self.clocks[col]
            to_move = self.board.turn == col and not self.over
            if self.clock_running() and to_move:
                bg, fg = ("#c0392b", "#ffffff") if sec < 10 else ("#ffffff", "#262421")
            elif to_move:
                bg, fg = "#989795", "#e9e8e7"           # waiting for the first move
            else:
                bg, fg = "#2b2925", "#8a8886" if sec >= 10 else "#d9cfcf"
            self.cv.itemconfig(rect, fill=bg)
            self.cv.itemconfig(txt, text=fmt_clock(sec), fill=fg)

    def flag(self, colour):
        if self.over:
            return
        self.cancel_engine()
        self.over, self.clocks[colour] = True, 0.0
        if self.board.has_insufficient_material(not colour):
            msg, res = "Time out, but the opponent cannot checkmate: draw.", 1
        elif colour == self.human:
            msg, res = "You ran out of time. The bot wins.", 2
        else:
            msg, res = "The bot ran out of time. You win! \U0001f389", 0
        self.record(res)
        self.update_clocks()
        self.set_status(msg)
        self.root.after(250, lambda: messagebox.showinfo(APP_NAME, msg))

    # ---------------------------------------------------------- game flow --
    def start_game(self, level, color, tc, ask=True):
        if ask and self.board.move_stack and not self.over:
            if not messagebox.askyesno(APP_NAME, "Abandon the current game and start a new one?"):
                return False
        self.cfg.update(level=level, color=color, tc=tc)
        save_cfg(self.cfg)
        self.cancel_engine()
        self.level_idx = [l[0] for l in LEVELS].index(level)
        self.sel = {"level": self.level_idx, "color": color, "tc": tc}
        self.tc_label = tc
        self.base, self.inc = TC.get(tc, (None, 0))
        self.clocks = {True: float(self.base or 0), False: float(self.base or 0)}
        self.last_t = None
        self.board = chess.Board()
        self.sans, self.over = [], False
        self.selected = self.hint = self.drag_from = None
        self.targets = set()
        if color == "Random":
            color = random.choice(["White", "Black"])
        self.human = chess.WHITE if color == "White" else chess.BLACK
        self.flipped = not self.human
        self.after_move()
        return True

    def cancel_engine(self):
        self.token += 1
        self.stop_ev.set()
        self.thinking = False

    def after_move(self):
        self.draw()
        self.update_panels()
        if self.check_end():
            return
        if self.board.turn != self.human:
            self.start_engine()
        else:
            self.set_status("Your move." + ("  Check!" if self.board.is_check() else ""))

    def play(self, move):
        self._charge()
        mover, first = self.board.turn, not self.board.move_stack
        self.sans.append(self.board.san(move))
        self.board.push(move)
        if self.base and not first:
            self.clocks[mover] += self.inc
        self.selected, self.hint, self.targets = None, None, set()
        self.after_move()

    def check_end(self):
        out = self.board.outcome(claim_draw=True)
        if not out:
            return False
        self.over = True
        T = chess.Termination
        if out.termination == T.CHECKMATE:
            win = out.winner == self.human
            msg = "Checkmate! " + ("You win \U0001f389" if win else "The bot wins.")
            self.record(0 if win else 2)
        else:
            msg = {T.STALEMATE: "Draw by stalemate.", T.INSUFFICIENT_MATERIAL: "Draw: insufficient material.",
                   T.THREEFOLD_REPETITION: "Draw by repetition.", T.FIFTY_MOVES: "Draw by the 50-move rule."}.get(out.termination, "Draw.")
            self.record(1)
        self.set_status(msg)
        self.update_clocks()
        self.root.after(250, lambda: messagebox.showinfo(APP_NAME, msg))
        return True

    def resign(self):
        if self.over or not self.board.move_stack:
            return
        if messagebox.askyesno(APP_NAME, "Resign this game?"):
            self.cancel_engine()
            self.over = True
            self.record(2)
            self.set_status("You resigned.")
            self.update_clocks()

    def undo(self):
        if not self.board.move_stack:
            return
        if self.base:
            self.set_status("Undo is only available in games with no timer.")
            return
        self.cancel_engine()
        self.over, n = False, 0
        while self.board.move_stack and (n == 0 or self.board.turn != self.human):
            self.board.pop()
            self.sans.pop()
            n += 1
        self.selected, self.hint, self.targets = None, None, set()
        self.after_move()

    def flip(self):
        self.flipped = not self.flipped
        self.draw()
        self.draw_rows()

    # ------------------------------------------------------------- engine --
    def start_engine(self):
        self.cancel_engine()
        self.stop_ev = threading.Event()
        self.thinking, tok, stop = True, self.token, self.stop_ev
        params = dict(LEVELS[self.level_idx][2])
        if self.base:
            params["think_time"] = min(params["think_time"], max(0.3, self.clocks[self.board.turn] / 25 + self.inc * 0.6))
        eng, snapshot = Engine(**params), self.board.copy()
        self.set_status("%s Bot is thinking\u2026" % LEVELS[self.level_idx][0])
        threading.Thread(target=lambda: self.q.put((tok, "move", eng.choose(snapshot, stop))), daemon=True).start()

    def get_hint(self):
        if self.over or self.thinking or self.board.turn != self.human:
            return
        self.token += 1
        tok, snapshot = self.token, self.board.copy()
        self.set_status("Looking for a good move\u2026")
        eng = Engine(depth=4, think_time=3)
        threading.Thread(target=lambda: self.q.put((tok, "hint", eng.choose(snapshot))), daemon=True).start()

    def _poll(self):
        try:
            tok, kind, mv = self.q.get_nowait()
            if tok == self.token and mv is not None and not self.over:
                if kind == "move":
                    self.thinking = False
                    self.play(mv)
                else:
                    self.hint = mv
                    self.set_status("Hint: %s" % self.board.san(mv))
                    self.draw()
        except queue.Empty:
            pass
        self.root.after(60, self._poll)

    # -------------------------------------------------------------- input --
    def can_move(self):
        return not self.over and not self.thinking and self.board.turn == self.human

    def on_press(self, e):
        sq = self.xy_sq(e.x, e.y)
        if sq is None or not self.can_move():
            return
        if self.selected is not None and sq in self.targets and self.try_move(self.selected, sq):
            return
        p = self.board.piece_at(sq)
        if p and p.color == self.human:
            self.selected, self.drag_from, self.hint = sq, sq, None
            self.targets = {m.to_square for m in self.board.legal_moves if m.from_square == sq}
        else:
            self.selected, self.targets = None, set()
        self.draw()
        if self.drag_from is not None:
            self.draw_piece(p, e.x, e.y, "ghost")

    def on_drag(self, e):
        if self.drag_from is None:
            return
        self.cv.delete("ghost")
        self.draw_piece(self.board.piece_at(self.drag_from), e.x, e.y, "ghost")

    def on_release(self, e):
        if self.drag_from is None:
            return
        src, self.drag_from = self.drag_from, None
        self.cv.delete("ghost")
        dst = self.xy_sq(e.x, e.y)
        if dst is not None and dst != src and dst in self.targets and self.try_move(src, dst):
            return
        self.draw()

    def try_move(self, frm, to):
        legal = [m for m in self.board.legal_moves if m.from_square == frm and m.to_square == to]
        if not legal:
            return False
        promo = self.ask_promotion() if legal[0].promotion else None
        self.play(chess.Move(frm, to, promo))
        return True

    # ------------------------------------------------------------ dialogs --
    def _popup(self, title):
        top = tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg=PANEL)
        top.transient(self.root)
        top.resizable(False, False)
        return top

    def _place(self, top, dx=60, dy=60):
        top.update_idletasks()
        top.geometry("+%d+%d" % (self.root.winfo_x() + dx, self.root.winfo_y() + dy))
        top.grab_set()

    def ask_promotion(self):
        top = self._popup("Promote pawn to")
        choice = {"v": chess.QUEEN}
        lt, dk, _ = THEMES[self.theme]

        def pick(pt):
            choice["v"] = pt
            top.destroy()
        for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            key = ("w" if self.human else "b") + SYM[pt]
            kw = dict(image=self.imgs[key]) if self.imgs else dict(text=GLYPH[pt], font=(self.pfont, 34))
            tk.Button(top, bg=dk, activebackground=lt, relief="flat", command=lambda p=pt: pick(p), **kw).pack(side="left", padx=4, pady=8)
        self._place(top, int(300 * self.k), int(300 * self.k))
        self.root.wait_window(top)
        return choice["v"]

    def open_themes(self):
        top = self._popup("Board Theme")
        tk.Label(top, text="Board Theme", bg=PANEL, fg=SEL, font=(self.ui, 18, "bold")).pack(anchor="w", padx=22, pady=(16, 8))
        grid = tk.Frame(top, bg=PANEL)
        grid.pack(padx=18, pady=(0, 12))
        cards = {}

        def apply(name):
            self.cfg["theme"] = self.theme = name
            self.tex = None
            save_cfg(self.cfg)
            for n, card in cards.items():
                card.config(highlightbackground=SEL if n == name else "#363532")
            self.draw()
        for i, (name, (lt, dk, wood)) in enumerate(THEMES.items()):
            card = tk.Frame(grid, bg="#363532", highlightthickness=3, cursor="hand2",
                            highlightbackground=SEL if name == self.theme else "#363532")
            card.grid(row=i // 2, column=i % 2, padx=6, pady=6)
            cv = tk.Canvas(card, width=192, height=96, bg="#363532", highlightthickness=0)
            cv.pack(padx=4, pady=(4, 0))
            for r in range(2):
                for c in range(4):
                    cv.create_rectangle(c * 48, r * 48, c * 48 + 48, r * 48 + 48, fill=lt if (r + c) % 2 == 0 else dk, outline="")
            if self.icons:
                cv.create_image(72, 24, image=self.icons["wN"])
                cv.create_image(120, 72, image=self.icons["bQ"])
                cv.create_image(24, 72, image=self.icons["wP"])
            tk.Label(card, text=name, bg="#363532", fg="#fff", font=(self.ui, 11, "bold")).pack(pady=(2, 6))
            for w in (card, cv) + tuple(card.winfo_children()):
                w.bind("<Button-1>", lambda e, n=name: apply(n))
            cards[name] = card
        done = tk.Label(top, text="Done", bg=GREEN_FACE, fg="#fff", font=(self.ui, 13, "bold"), pady=10, cursor="hand2")
        done.bind("<Button-1>", lambda e: top.destroy())
        done.pack(fill="x", padx=24, pady=(0, 16))
        self._place(top, int(200 * self.k), int(150 * self.k))


def main():
    root = tk.Tk()
    ChessApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
