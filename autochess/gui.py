"""The Auto-chess screen: a start screen (play the robot, or watch it play itself) and a game screen."""
import queue
import random
import tkinter as tk

import chess

from . import results
from .clock import TIME_PRESETS, fmt
from .engine import LEVEL_NAMES
from .game import Game, Player, side_name

MAROON, GOLD, CREAM = "#501214", "#8D734A", "#F4EFE6"
LIGHT_SQ, DARK_SQ, PICK_SQ, LAST_SQ = "#EBD9B4", "#A97C50", "#E8C547", "#C9B458"
RED = "#B3261E"
SQ = 72                     # board square size on screen, pixels
ROBOT_NAME = "Robo"
NAME_MAX = 20

SOLID = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
OUTLINE = {"k": "♔", "q": "♕", "r": "♖", "b": "♗", "n": "♘", "p": "♙"}


def font(size, bold=False):
    return ("Helvetica", size, "bold") if bold else ("Helvetica", size)


def choice_buttons(parent, var, options, **kw):
    """A row of big toggle buttons, one per option, sharing var."""
    row = tk.Frame(parent, bg=CREAM)
    for opt in options:
        tk.Radiobutton(row, text=str(opt), value=opt, variable=var, indicatoron=False, font=font(15),
                       width=kw.get("width", 9), pady=6, selectcolor=GOLD, bg="white", fg=MAROON,
                       activebackground=GOLD).pack(side="left", padx=3)
    return row


class App:
    def __init__(self, root, engine, arm, eyes, clickable=False):
        self.root, self.engine, self.arm, self.eyes = root, engine, arm, eyes
        self.clickable = clickable    # pretend eyes: the human clicks their move on the screen
        self.events = queue.Queue()
        self.game = None
        self.frame = None
        root.title("Auto-chess")
        root.configure(bg=CREAM)
        root.minsize(1000, 720)
        self.show_start()
        self._poll()

    def _swap(self):
        if self.frame:
            self.frame.destroy()
        self.frame = tk.Frame(self.root, bg=CREAM)
        self.frame.pack(fill="both", expand=True)
        return self.frame

    def _header(self, parent, text):
        tk.Label(parent, text=text, font=font(28, True), bg=MAROON, fg="white", pady=12).pack(fill="x")

    # ---------------- start screen ----------------
    def show_start(self):
        f = self._swap()
        self._header(f, "Auto-chess")
        body = tk.Frame(f, bg=CREAM)
        body.pack(fill="both", expand=True, padx=30, pady=20)
        left = tk.Frame(body, bg=CREAM)
        left.pack(side="left", fill="both", expand=True)

        self.mode = tk.StringVar(value="human")
        tk.Label(left, text="Mode", font=font(16, True), bg=CREAM, fg=MAROON).pack(anchor="w")
        modes = tk.Frame(left, bg=CREAM)
        modes.pack(anchor="w", pady=(2, 14))
        for value, text in (("human", "Play the robot"), ("robot", "Watch robot vs robot")):
            tk.Radiobutton(modes, text=text, value=value, variable=self.mode, indicatoron=False,
                           font=font(16, True), width=18, pady=8, selectcolor=GOLD, bg="white", fg=MAROON,
                           command=self._show_mode).pack(side="left", padx=3)

        self.options = tk.Frame(left, bg=CREAM)
        self.options.pack(anchor="w", fill="x")
        self.name = tk.StringVar()
        self.level = tk.StringVar(value="Easy")
        self.colour = tk.StringVar(value="White")
        self.white_level = tk.StringVar(value="Hard")
        self.black_level = tk.StringVar(value="Medium")
        self.minutes = tk.IntVar(value=TIME_PRESETS[0])
        self.error = tk.Label(left, text="", font=font(14), bg=CREAM, fg=RED)
        self._show_mode()
        self.error.pack(anchor="w", pady=(10, 0))
        tk.Button(left, text="Start", font=font(20, True), bg=MAROON, fg="white", activebackground=GOLD,
                  highlightbackground=MAROON, width=14, pady=8, command=self._start).pack(anchor="w", pady=16)

        self._leaderboard(body)

    def _label(self, parent, text):
        tk.Label(parent, text=text, font=font(16, True), bg=CREAM, fg=MAROON).pack(anchor="w", pady=(10, 2))

    def _show_mode(self):
        for w in self.options.winfo_children():
            w.destroy()
        o = self.options
        if self.mode.get() == "human":
            self._label(o, "Your name")
            entry = tk.Entry(o, textvariable=self.name, font=font(18), width=24)
            entry.pack(anchor="w")
            entry.focus_set()
            self._label(o, "Difficulty")
            choice_buttons(o, self.level, LEVEL_NAMES).pack(anchor="w")
            self._label(o, "Your colour")
            choice_buttons(o, self.colour, ["White", "Black", "Random"]).pack(anchor="w")
        else:
            self._label(o, "White's difficulty")
            choice_buttons(o, self.white_level, LEVEL_NAMES).pack(anchor="w")
            self._label(o, "Black's difficulty")
            choice_buttons(o, self.black_level, LEVEL_NAMES).pack(anchor="w")
        self._label(o, "Time per side (minutes)")
        choice_buttons(o, self.minutes, TIME_PRESETS, width=6).pack(anchor="w")

    def _leaderboard(self, parent):
        box = tk.Frame(parent, bg="white", highlightbackground=GOLD, highlightthickness=2)
        box.pack(side="right", fill="y", padx=(20, 0))
        tk.Label(box, text="Leaderboard", font=font(18, True), bg=GOLD, fg="white", pady=6).pack(fill="x")
        tk.Label(box, text="Wins against the robot", font=font(12), bg="white", fg=MAROON).pack(pady=(4, 0))
        board = results.leaderboard(results.load())
        for level in LEVEL_NAMES:
            tk.Label(box, text=level, font=font(15, True), bg="white", fg=MAROON, anchor="w").pack(
                fill="x", padx=14, pady=(10, 0))
            rows = board.get(level) or [("no wins yet", None)]
            for i, (name, wins) in enumerate(rows, 1):
                text = f"{i}. {name}  ({wins})" if wins else name
                tk.Label(box, text=text, font=font(13), bg="white", anchor="w", width=26).pack(fill="x", padx=24)

    def _start(self):
        minutes = self.minutes.get()
        if minutes < 10:     # the presets never allow this; kept as a guard
            self.error.config(text="Games are at least 10 minutes.")
            return
        if self.mode.get() == "human":
            name = " ".join(self.name.get().split())
            if not name:
                self.error.config(text="Please type your name.")
                return
            if len(name) > NAME_MAX:
                self.error.config(text=f"Please use at most {NAME_MAX} letters.")
                return
            colour = self.colour.get()
            if colour == "Random":
                colour = random.choice(["White", "Black"])
            human = Player("human", name)
            robot = Player("robot", f"{ROBOT_NAME} ({self.level.get()})", self.level.get())
            white, black = (human, robot) if colour == "White" else (robot, human)
        else:
            white = Player("robot", f"{ROBOT_NAME} White ({self.white_level.get()})", self.white_level.get())
            black = Player("robot", f"{ROBOT_NAME} Black ({self.black_level.get()})", self.black_level.get())
        self.game = Game(white, black, minutes, self.engine, self.arm, self.eyes,
                         on_event=lambda kind, data: self.events.put((kind, data)))
        self.show_game()
        self.game.start()

    # ---------------- game screen ----------------
    def show_game(self):
        g = self.game
        human_sides = [s for s, p in g.players.items() if p.kind == "human"]
        self.bottom = human_sides[0] if human_sides else chess.WHITE    # this side sits at the bottom
        self.picked = None          # square clicked first (pretend eyes)
        self.pending = None         # move clicked, waiting for Done
        self.last = None

        f = self._swap()
        w, b = g.players[chess.WHITE], g.players[chess.BLACK]
        self._header(f, f"{w.name}  vs  {b.name}")
        body = tk.Frame(f, bg=CREAM)
        body.pack(fill="both", expand=True, padx=20, pady=14)

        self.canvas = tk.Canvas(body, width=8 * SQ + 24, height=8 * SQ + 24, bg=MAROON, highlightthickness=0)
        self.canvas.pack(side="left")
        if self.clickable:
            self.canvas.bind("<Button-1>", self._click)

        side = tk.Frame(body, bg=CREAM)
        side.pack(side="left", fill="both", expand=True, padx=(20, 0))
        self.clock_labels = {}
        self._clock_row(side, not self.bottom)
        self.status = tk.Label(side, text="", font=font(17, True), bg=CREAM, fg=MAROON, wraplength=360,
                               justify="left", height=4, anchor="w")
        self.status.pack(fill="x", pady=8)
        self.moves = tk.Listbox(side, font=("Courier", 15), height=10, bg="white", fg=MAROON,
                                highlightthickness=0)
        self.moves.pack(fill="both", expand=True)
        self._clock_row(side, self.bottom)

        buttons = tk.Frame(side, bg=CREAM)
        buttons.pack(fill="x", pady=(10, 0))
        if human_sides:
            self.done_btn = tk.Button(buttons, text="Done", font=font(22, True), bg=GOLD, fg="white",
                                      highlightbackground=GOLD, width=9, pady=10, state="disabled",
                                      command=self._done)
            self.done_btn.pack(side="left")
            tk.Button(buttons, text="Resign", font=font(15), width=8, pady=12,
                      command=lambda: g.resign(human_sides[0])).pack(side="right")
        else:
            self.done_btn = None
            tk.Button(buttons, text="Stop game", font=font(15), width=10, pady=12,
                      command=g.stop).pack(side="right")
        self.root.bind("<Return>", lambda e: self._done())
        self.root.bind("<space>", lambda e: self._done())
        self._draw()
        self._tick()

    def _clock_row(self, parent, side):
        row = tk.Frame(parent, bg=CREAM)
        row.pack(fill="x", pady=4)
        p = self.game.players[side]
        tk.Label(row, text=f"{side_name(side)}: {p.name}", font=font(16, True), bg=CREAM, fg=MAROON).pack(
            side="left")
        lbl = tk.Label(row, text="", font=("Courier", 30, "bold"), width=6, bg="white", fg=MAROON)
        lbl.pack(side="right")
        self.clock_labels[side] = lbl

    def _tick(self):
        if not self.game or not self.frame.winfo_exists() or not hasattr(self, "clock_labels"):
            return
        for side, lbl in self.clock_labels.items():
            if not lbl.winfo_exists():
                return
            running = self.game.clock.running == side
            lbl.config(text=fmt(self.game.clock.left(side)), bg=GOLD if running else "white",
                       fg="white" if running else MAROON)
        self.root.after(200, self._tick)

    def _xy(self, square):
        """Top-left pixel of a square, with self.bottom's side at the bottom."""
        f, r = chess.square_file(square), chess.square_rank(square)
        if self.bottom == chess.WHITE:
            col, row = f, 7 - r
        else:
            col, row = 7 - f, r
        return 12 + col * SQ, 12 + row * SQ

    def _square_at(self, x, y):
        col, row = (x - 12) // SQ, (y - 12) // SQ
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        return chess.square(col, 7 - row) if self.bottom == chess.WHITE else chess.square(7 - col, row)

    def _draw(self):
        c, board = self.canvas, self.game.board
        c.delete("all")
        marks = set()
        if self.last:
            marks |= {self.last.from_square, self.last.to_square}
        for sq in chess.SQUARES:
            x, y = self._xy(sq)
            colour = LIGHT_SQ if (chess.square_file(sq) + chess.square_rank(sq)) % 2 else DARK_SQ
            if sq in marks:
                colour = LAST_SQ
            if self.pending and sq in (self.pending.from_square, self.pending.to_square):
                colour = PICK_SQ
            if sq == self.picked:
                colour = PICK_SQ
            c.create_rectangle(x, y, x + SQ, y + SQ, fill=colour, width=0)
            piece = board.piece_at(sq)
            if self.pending and sq == self.pending.from_square:
                piece = None
            if self.pending and sq == self.pending.to_square:
                piece = board.piece_at(self.pending.from_square)
            if piece:
                self._piece(x + SQ / 2, y + SQ / 2, piece)
        for i in range(8):     # file letters and rank numbers
            fx, _ = self._xy(chess.square(i, 0))
            _, ry = self._xy(chess.square(0, i))
            c.create_text(fx + SQ / 2, 8 * SQ + 18, text="abcdefgh"[i], fill="white", font=font(10, True))
            c.create_text(6, ry + SQ / 2, text=str(i + 1), fill="white", font=font(10, True))

    def _piece(self, x, y, piece):
        s = piece.symbol().lower()
        if piece.color == chess.WHITE:
            self.canvas.create_text(x, y + 2, text=SOLID[s], font=("DejaVu Sans", 46), fill="white")
            self.canvas.create_text(x, y + 2, text=OUTLINE[s], font=("DejaVu Sans", 46), fill="black")
        else:
            self.canvas.create_text(x, y + 2, text=SOLID[s], font=("DejaVu Sans", 46), fill="black")

    def _human_to_move(self):
        g = self.game
        return g and g.result is None and g.players[g.board.turn].kind == "human"

    def _click(self, event):
        if not self._human_to_move():
            return
        sq = self._square_at(event.x, event.y)
        if sq is None:
            return
        board = self.game.board
        piece = board.piece_at(sq)
        if self.picked is None or (piece and piece.color == board.turn):
            self.picked = sq if piece and piece.color == board.turn else None
            self.pending = None
        else:
            move = chess.Move(self.picked, sq)
            if board.piece_type_at(self.picked) == chess.PAWN and chess.square_rank(sq) in (0, 7):
                move.promotion = chess.QUEEN
            self.picked = None
            if move in board.legal_moves:
                self.pending = move
                self.eyes.set_move(move)
                self._say("Press Done to finish your move.")
            else:
                self.pending = None
                self._say("That move isn't allowed. Try another.", RED)
        self._draw()

    def _done(self):
        if self._human_to_move() and self.done_btn and str(self.done_btn["state"]) == "normal":
            self.done_btn.config(state="disabled")
            self.game.press_done()

    def _say(self, text, colour=MAROON):
        self.status.config(text=text, fg=colour)

    # ---------------- game events (from the game thread) ----------------
    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                self._handle(kind, data)
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _handle(self, kind, data):
        if not self.game or not hasattr(self, "status") or not self.status.winfo_exists():
            return
        g = self.game
        if kind == "turn":
            p = data["player"]
            if p.kind == "human":
                how = "click a piece, then its square" if self.clickable else "move a piece on the board"
                self._say(f"Your move, {p.name}: {how}, then press Done.")
                self.done_btn.config(state="normal")
        elif kind == "thinking":
            self._say(f"{g.players[data['side']].name} is thinking...")
        elif kind == "arm":
            self._say(f"{g.players[data['side']].name} plays {data['san']}. The arm is moving...")
        elif kind == "bad_move":
            self.pending = None
            self._draw()
            self._say("I couldn't see a legal move. Check the board, then press Done again.", RED)
            self.done_btn.config(state="normal")
        elif kind == "moved":
            self.last, self.pending = data["move"], None
            n = len(g.board.move_stack)
            if data["side"] == chess.WHITE:
                self.moves.insert("end", f"{(n + 1) // 2:3d}. {data['san']}")
            else:
                if self.moves.size() == 0:
                    self.moves.insert("end", f"{(n + 1) // 2:3d}. ...")
                last = self.moves.get("end")
                self.moves.delete("end")
                self.moves.insert("end", f"{last:<14}{data['san']}")
            self.moves.see("end")
            self._draw()
        elif kind == "game_over":
            self._game_over(data)

    def _game_over(self, data):
        g = self.game
        if g.result != "*":
            results.save(g)
        if self.done_btn:
            self.done_btn.config(state="disabled")
        winner = g.winner_name()
        title = {"1-0": f"{winner} wins!", "0-1": f"{winner} wins!", "1/2-1/2": "Draw"}.get(g.result, "Game stopped")
        over = tk.Frame(self.frame, bg=MAROON, padx=40, pady=30)
        over.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(over, text=title, font=font(32, True), bg=MAROON, fg="white").pack()
        tk.Label(over, text=data["reason"], font=font(17), bg=MAROON, fg=CREAM).pack(pady=(6, 18))
        tk.Button(over, text="Back to start", font=font(17, True), bg=GOLD, fg="white",
                  highlightbackground=MAROON, pady=8, command=self._back).pack()

    def _back(self):
        if self.game and self.game.result is None:
            self.game.stop()
        self.game = None
        self.root.unbind("<Return>")
        self.root.unbind("<space>")
        self.show_start()
