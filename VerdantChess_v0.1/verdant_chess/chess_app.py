#!/usr/bin/env python3
"""
Verdant Chess  -  an offline chess game with a green & white, chess.com-style look.

Run:   python chess_app.py          (needs:  pip install chess)
Build: see README.md (PyInstaller -> single double-clickable app)
"""
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont

import chess

APP_NAME = "Verdant Chess"

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
        if self.nodes & 511 == 0 and (self.stop.is_set() or time.time() > self.deadline):
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
        self.nodes = 0
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
#  GUI  (tkinter - ships with Python, works fully offline)
# =============================================================================
LIGHT, DARK = "#eeeed2", "#769656"
HL_LIGHT, HL_DARK = "#f5f682", "#b9ca43"
BG, PANEL, PANEL2 = "#312e2b", "#262421", "#3d3a37"
GREEN, GREEN_HOVER = "#81b64c", "#a3d160"
TEXT, MUTED = "#ffffff", "#bababa"
GLYPH = {chess.PAWN: "\u265f\ufe0e", chess.KNIGHT: "\u265e", chess.BISHOP: "\u265d",
         chess.ROOK: "\u265c", chess.QUEEN: "\u265b", chess.KING: "\u265a"}
START_COUNT = {chess.QUEEN: 1, chess.ROOK: 2, chess.BISHOP: 2, chess.KNIGHT: 2, chess.PAWN: 8}


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def make_button(parent, text, cmd, primary=False):
    bg = GREEN if primary else PANEL2
    hover = GREEN_HOVER if primary else "#504d4a"
    lab = tk.Label(parent, text=text, bg=bg, fg=TEXT, cursor="hand2", padx=10, pady=9,
                   font=("Segoe UI", 11, "bold"))
    lab.bind("<Button-1>", lambda e: cmd())
    lab.bind("<Enter>", lambda e: lab.config(bg=hover))
    lab.bind("<Leave>", lambda e: lab.config(bg=bg))
    return lab


class ChessApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.configure(bg=BG)
        root.resizable(False, False)
        self.S = max(48, min(84, (root.winfo_screenheight() - 200) // 8))
        fams = set(tkfont.families())
        self.pfont = next((f for f in ("Segoe UI Symbol", "Apple Symbols", "DejaVu Sans",
                                       "Arial Unicode MS", "FreeSerif") if f in fams), "TkDefaultFont")
        self.board = chess.Board()
        self.human = chess.WHITE
        self.level_idx = 2
        self.flipped = False
        self.selected = self.drag_from = self.hint = None
        self.targets = set()
        self.sans = []
        self.over = False
        self.thinking = False
        self.token = 0
        self.stop_ev = threading.Event()
        self.q = queue.Queue()
        self._build_ui()
        self.new_game()
        self._poll()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self):
        S = self.S
        left = tk.Frame(self.root, bg=BG)
        left.grid(row=0, column=0, padx=(16, 8), pady=14)
        self.top_name = tk.Label(left, bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold"), anchor="w")
        self.top_name.pack(fill="x")
        self.top_cap = tk.Label(left, bg=BG, fg=MUTED, font=(self.pfont, 14), anchor="w")
        self.top_cap.pack(fill="x")
        self.cv = tk.Canvas(left, width=8 * S, height=8 * S, bg=BG, highlightthickness=0)
        self.cv.pack(pady=4)
        self.bot_cap = tk.Label(left, bg=BG, fg=MUTED, font=(self.pfont, 14), anchor="w")
        self.bot_cap.pack(fill="x")
        self.bot_name = tk.Label(left, bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold"), anchor="w")
        self.bot_name.pack(fill="x")
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)

        right = tk.Frame(self.root, bg=PANEL, width=300)
        right.grid(row=0, column=1, sticky="ns", padx=(8, 16), pady=14)
        tk.Label(right, text="\u265e  " + APP_NAME, bg=PANEL, fg=GREEN,
                 font=("Segoe UI", 17, "bold")).pack(padx=16, pady=(14, 6), anchor="w")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2,
                        foreground=TEXT, arrowcolor=TEXT, bordercolor=PANEL2, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL2)],
                  foreground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", PANEL2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", GREEN)

        opt = tk.Frame(right, bg=PANEL)
        opt.pack(fill="x", padx=16)
        tk.Label(opt, text="Opponent level", bg=PANEL, fg=MUTED, anchor="w").pack(fill="x")
        self.level_var = tk.StringVar(value=LEVELS[self.level_idx][0])
        cb = ttk.Combobox(opt, textvariable=self.level_var, state="readonly",
                          values=[l[0] for l in LEVELS], font=("Segoe UI", 11))
        cb.pack(fill="x", pady=(2, 2))
        cb.bind("<<ComboboxSelected>>", lambda e: self._level_changed())
        self.level_desc = tk.Label(opt, bg=PANEL, fg=MUTED, wraplength=268, justify="left",
                                   anchor="w", font=("Segoe UI", 9))
        self.level_desc.pack(fill="x", pady=(0, 6))
        tk.Label(opt, text="Play as", bg=PANEL, fg=MUTED, anchor="w").pack(fill="x")
        self.color_var = tk.StringVar(value="White")
        ttk.Combobox(opt, textvariable=self.color_var, state="readonly",
                     values=["White", "Black", "Random"], font=("Segoe UI", 11)).pack(fill="x", pady=2)

        make_button(right, "\u25b6  New Game", self.confirm_new, True).pack(fill="x", padx=16, pady=(10, 6))

        mv = tk.Frame(right, bg=PANEL2)
        mv.pack(fill="both", expand=True, padx=16, pady=4)
        self.moves = tk.Text(mv, width=28, height=12, bg=PANEL2, fg=TEXT, relief="flat", bd=0,
                             font=("Consolas", 11), state="disabled", padx=8, pady=6, cursor="arrow")
        sb = tk.Scrollbar(mv, command=self.moves.yview)
        self.moves.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.moves.pack(side="left", fill="both", expand=True)

        self.status = tk.Label(right, bg=PANEL, fg=TEXT, wraplength=268, justify="left",
                               anchor="w", font=("Segoe UI", 11, "bold"), height=2)
        self.status.pack(fill="x", padx=16, pady=(6, 2))

        row = tk.Frame(right, bg=PANEL)
        row.pack(fill="x", padx=16, pady=(2, 14))
        for i, (t, c) in enumerate((("\u21b6 Undo", self.undo), ("\U0001f4a1 Hint", self.get_hint),
                                    ("\u21c5 Flip", self.flip), ("\u2690 Resign", self.resign))):
            b = make_button(row, t, c)
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
            row.grid_columnconfigure(i % 2, weight=1)

    def _level_changed(self):
        self.level_idx = [l[0] for l in LEVELS].index(self.level_var.get())
        self.level_desc.config(text=LEVELS[self.level_idx][1])

    # ---------------------------------------------------------- geometry --
    def sq_xy(self, sq):
        f, r, S = chess.square_file(sq), chess.square_rank(sq), self.S
        return ((7 - f) * S, r * S) if self.flipped else (f * S, (7 - r) * S)

    def xy_sq(self, x, y):
        col, row = int(x // self.S), int(y // self.S)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        f, r = (7 - col, row) if self.flipped else (col, 7 - row)
        return chess.square(f, r)

    # ----------------------------------------------------------- drawing --
    def draw_piece(self, piece, cx, cy, tag):
        g = GLYPH[piece.piece_type]
        size = int(self.S * 0.74)
        fill, edge = ("#ffffff", "#2b2b2b") if piece.color else ("#1d1d1d", "#000000")
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1.5, -1.5), (1.5, 1.5), (-1.5, 1.5), (1.5, -1.5)):
            self.cv.create_text(cx + dx, cy + dy, text=g, font=(self.pfont, size), fill=edge, tags=tag)
        self.cv.create_text(cx, cy, text=g, font=(self.pfont, size), fill=fill, tags=tag)

    def draw(self):
        c, S, b = self.cv, self.S, self.board
        c.delete("all")
        last = b.peek() if b.move_stack else None
        check_sq = b.king(b.turn) if b.is_check() else None
        small = ("Segoe UI", max(8, S // 7), "bold")
        for sq in range(64):
            f, r = chess.square_file(sq), chess.square_rank(sq)
            x, y = self.sq_xy(sq)
            light = (f + r) % 2 == 1
            col = LIGHT if light else DARK
            if (last and sq in (last.from_square, last.to_square)) or sq == self.selected:
                col = HL_LIGHT if light else HL_DARK
            if sq == check_sq:
                col = blend(col, "#e63946", 0.65)
            c.create_rectangle(x, y, x + S, y + S, fill=col, outline="")
            lab = DARK if light else LIGHT
            if x == (7 * S if self.flipped else 0):
                c.create_text(x + 4, y + 3, text=str(r + 1), anchor="nw", font=small, fill=lab)
            if y == (0 if self.flipped else 7 * S):
                c.create_text(x + S - 4, y + S - 3, text="abcdefgh"[f], anchor="se", font=small, fill=lab)
            if sq in self.targets:
                dot = blend(col, "#000000", 0.18)
                if b.piece_at(sq) or b.is_en_passant(chess.Move(self.selected, sq)):
                    c.create_oval(x + 3, y + 3, x + S - 3, y + S - 3, outline=dot, width=max(4, S // 12))
                else:
                    r0 = S * 0.17
                    c.create_oval(x + S / 2 - r0, y + S / 2 - r0, x + S / 2 + r0, y + S / 2 + r0,
                                  fill=dot, outline="")
        for sq, p in b.piece_map().items():
            if sq == self.drag_from:
                continue
            x, y = self.sq_xy(sq)
            self.draw_piece(p, x + S / 2, y + S / 2, "piece")
        if self.hint:
            x1, y1 = self.sq_xy(self.hint.from_square)
            x2, y2 = self.sq_xy(self.hint.to_square)
            c.create_line(x1 + S / 2, y1 + S / 2, x2 + S / 2, y2 + S / 2, arrow="last",
                          width=S * 0.13, fill="#f0a21e", arrowshape=(S * .3, S * .3, S * .15))

    def update_panels(self):
        b = self.board
        opp = not self.human
        lv = LEVELS[self.level_idx][0]
        self.top_name.config(text="\U0001f916  %s Bot" % lv)
        self.bot_name.config(text="\U0001f464  You (%s)" % ("White" if self.human else "Black"))
        lost = {col: [] for col in (True, False)}
        for col in (True, False):
            for pt, n in START_COUNT.items():
                lost[col] += [pt] * max(0, n - len(b.pieces(pt, col)))
        val = lambda cols: sum(PV[p] for p in lost[cols])
        adv = (val(opp) - val(self.human)) // 100        # >0: human is ahead
        order = lambda lst: "".join(GLYPH[p] for p in sorted(lst, key=lambda p: -PV[p]))
        self.bot_cap.config(text=order(lost[opp]) + ("   +%d" % adv if adv > 0 else ""))
        self.top_cap.config(text=order(lost[self.human]) + ("   +%d" % -adv if adv < 0 else ""))
        t = self.moves
        t.config(state="normal")
        t.delete("1.0", "end")
        for i in range(0, len(self.sans), 2):
            pair = self.sans[i:i + 2]
            t.insert("end", "%3d. %-8s %s\n" % (i // 2 + 1, pair[0], pair[1] if len(pair) > 1 else ""))
        t.config(state="disabled")
        t.see("end")

    def set_status(self, s):
        self.status.config(text=s)

    # --------------------------------------------------------- game flow --
    def confirm_new(self):
        if self.board.move_stack and not self.over:
            if not messagebox.askyesno(APP_NAME, "Abandon the current game and start a new one?"):
                return
        self.new_game()

    def new_game(self):
        self.cancel_engine()
        self.board = chess.Board()
        self.sans, self.over = [], False
        self.selected = self.hint = self.drag_from = None
        self.targets = set()
        pick = self.color_var.get() if hasattr(self, "color_var") else "White"
        if pick == "Random":
            pick = random.choice(["White", "Black"])
        self.human = chess.WHITE if pick == "White" else chess.BLACK
        self.flipped = not self.human
        self._level_changed()
        self.after_move()

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
        self.sans.append(self.board.san(move))
        self.board.push(move)
        self.selected, self.hint, self.targets = None, None, set()
        self.after_move()

    def check_end(self):
        out = self.board.outcome(claim_draw=True)
        if not out:
            return False
        self.over = True
        T = chess.Termination
        if out.termination == T.CHECKMATE:
            msg = "Checkmate! " + ("You win \U0001f389" if out.winner == self.human else "The bot wins.")
        else:
            msg = {T.STALEMATE: "Draw by stalemate.", T.INSUFFICIENT_MATERIAL: "Draw: insufficient material.",
                   T.THREEFOLD_REPETITION: "Draw by repetition.",
                   T.FIFTY_MOVES: "Draw by the 50-move rule."}.get(out.termination, "Draw.")
        self.set_status(msg)
        self.root.after(250, lambda: messagebox.showinfo(APP_NAME, msg))
        return True

    def resign(self):
        if self.over or not self.board.move_stack:
            return
        if messagebox.askyesno(APP_NAME, "Resign this game?"):
            self.cancel_engine()
            self.over = True
            self.set_status("You resigned.")

    def undo(self):
        if not self.board.move_stack:
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

    # ------------------------------------------------------------ engine --
    def start_engine(self):
        self.cancel_engine()
        self.stop_ev = threading.Event()
        self.thinking, tok, stop = True, self.token, self.stop_ev
        eng = Engine(**LEVELS[self.level_idx][2])
        snapshot = self.board.copy()
        self.set_status("%s is thinking\u2026" % LEVELS[self.level_idx][0])
        threading.Thread(target=lambda: self.q.put((tok, "move", eng.choose(snapshot, stop))),
                         daemon=True).start()

    def get_hint(self):
        if self.over or self.thinking or self.board.turn != self.human:
            return
        self.token += 1
        tok, snapshot = self.token, self.board.copy()
        self.set_status("Looking for a good move\u2026")
        eng = Engine(depth=4, think_time=3)
        threading.Thread(target=lambda: self.q.put((tok, "hint", eng.choose(snapshot))),
                         daemon=True).start()

    def _poll(self):
        try:
            tok, kind, mv = self.q.get_nowait()
            if tok == self.token and mv is not None:
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

    # ------------------------------------------------------------- input --
    def can_move(self):
        return not self.over and not self.thinking and self.board.turn == self.human

    def on_press(self, e):
        if not self.can_move():
            return
        sq = self.xy_sq(e.x, e.y)
        if sq is None:
            return
        if self.selected is not None and sq in self.targets:
            if self.try_move(self.selected, sq):
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
        promo = None
        legal = [m for m in self.board.legal_moves if m.from_square == frm and m.to_square == to]
        if not legal:
            return False
        if legal[0].promotion:
            promo = self.ask_promotion()
        self.play(chess.Move(frm, to, promo))
        return True

    def ask_promotion(self):
        top = tk.Toplevel(self.root)
        top.title("Promote pawn to")
        top.configure(bg=PANEL)
        top.transient(self.root)
        top.resizable(False, False)
        choice = {"v": chess.QUEEN}

        def pick(pt):
            choice["v"] = pt
            top.destroy()
        for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            tk.Button(top, text=GLYPH[pt], font=(self.pfont, 34), width=2,
                      fg="#ffffff" if self.human else "#000000", bg=DARK if self.human else LIGHT,
                      command=lambda p=pt: pick(p)).pack(side="left", padx=4, pady=8)
        top.update_idletasks()
        top.geometry("+%d+%d" % (self.root.winfo_x() + 120, self.root.winfo_y() + 200))
        top.grab_set()
        self.root.wait_window(top)
        return choice["v"]


def main():
    root = tk.Tk()
    ChessApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
