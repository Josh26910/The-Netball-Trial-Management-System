"""
main.py v2.1

Down to three files total now: this one (GUI + auth + styling), algorithm.py
(rotation engine), and players.py (everything about player/trial data).
auth.py and gui_components.py got folded directly into this file below,
since neither was used anywhere else - a coach or referee logging in only
matters to the GUI, and the theming only matters to the GUI.

Added since last commit (merged in from a more advanced reference copy of
this project, after verifying each claim rather than trusting it blindly):
    - Login now uses salted password hashing (hmac.compare_digest,
      per-account salt) instead of plain SHA-256 - see hash_password()
    - DOB/age eligibility (FR3): trials can optionally set a birth year
      range, and the Players tab shows live green/red feedback as the
      coordinator types a DOB - informational only, never blocks
      registration, since a permit can override it
    - Database backup: a dated copy is taken automatically on startup
      (contingency plan for corruption), plus a manual "Back Up Database
      Now" button on the Export tab

NOTE: can_edit() exists below but isn't wired up into the GUI yet - a coach
or referee on the Rounds tab currently has the same view as a coordinator
even though referees should be read-only. That's a follow-up, not solved
in this commit.
"""

import hashlib
import hmac
import secrets
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import players as database
import algorithm

POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]


# --------------------------------------------------------------------------- #
# AUTH & ROLE-BASED ACCESS CONTROL (previously auth.py)
# --------------------------------------------------------------------------- #
# Passwords are never stored in plain text - SHA-256 hash only. A `User`
# object represents the logged-in session and knows which tabs its role is
# allowed to see (has_access) and edit (can_edit). login() checks
# username + password + selected role against the users table.
#
# This is a first pass - just enough for a working login screen and to hide
# tabs the current role shouldn't see. No signup screen yet (accounts get
# created straight in the database - see players.init_db() for the default
# coordinator account), and can_edit() isn't wired into the GUI to actually
# disable buttons yet, just defined ready for when that gets added.

VALID_ROLES = ("coordinator", "coach", "referee", "player")

# Which of the five dashboard tabs each role is allowed to open.
ROLE_PERMISSIONS = {
    "coordinator": {"Trials", "Players", "Roll Call", "Rounds", "Export"},
    "coach":       {"Rounds"},
    "referee":     {"Rounds"},
    "player":      {"Players"},
}

# Whether a role may edit data on a tab it can see, vs. read-only.
# Not enforced in the GUI yet - defined here so it's ready to wire up.
ROLE_CAN_EDIT = {
    "coordinator": {"Trials", "Players", "Roll Call", "Rounds", "Export"},
    "coach":       {"Rounds"},
    "referee":     set(),
    "player":      {"Players"},
}


def new_salt():
    return secrets.token_hex(16)


def hash_password(plain_password, salt_hex):
    """
    Returns SHA-256(salt + password) as 64 hex characters. Each account
    gets its own random salt (see new_salt(), used when the account is
    created) rather than hashing the password alone - two accounts with
    the same password would otherwise share a hash, and an attacker with
    the database file could just compare against a precomputed table of
    common password hashes. The salt itself isn't secret; it's stored
    right alongside the hash in the users table.
    """
    salted = bytes.fromhex(salt_hex) + plain_password.encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def verify_password(plain_password, salt_hex, stored_hash):
    """Uses hmac.compare_digest rather than == so the time taken to reject
    a wrong password doesn't leak how many leading characters matched."""
    return hmac.compare_digest(hash_password(plain_password, salt_hex or ""), stored_hash)


def has_access(role, tab_name):
    return tab_name in ROLE_PERMISSIONS.get(role, set())


def can_edit(role, tab_name):
    return tab_name in ROLE_CAN_EDIT.get(role, set())


class User:
    """Represents the currently logged-in user for the duration of a session."""

    def __init__(self, user_id, username, role):
        self.user_id = user_id
        self.username = username
        self.role = role

    def has_access(self, tab_name):
        return has_access(self.role, tab_name)

    def can_edit(self, tab_name):
        return can_edit(self.role, tab_name)

    def display_role(self):
        return {
            "coordinator": "Coordinator",
            "coach": "Coach",
            "referee": "Referee",
            "player": "Player/Parent",
        }.get(self.role, self.role.title())


def login(username, password, role):
    """
    Checks username + password + the role picked on the login screen
    against the users table. Returns a User on success, None on failure.

    Deliberately doesn't say WHICH part was wrong (unknown username vs
    wrong password vs wrong role) in the return value - the login screen
    just shows one generic error message either way, so someone guessing
    usernames can't use the error message to figure out which ones exist.
    """
    record = database.get_user_by_username(username.strip())
    if not record:
        return None
    if record["role"] != role:
        return None
    if not verify_password(password, record.get("salt", ""), record["password_hash"]):
        return None
    return User(record["user_id"], record["username"], record["role"])


# --------------------------------------------------------------------------- #
# THEMING & SHARED WIDGETS (previously gui_components.py)
# --------------------------------------------------------------------------- #
# Applies the visual language from the mood board and detailed designs
# (Criteria 4/5): navy header (#1f3864), white workspace, alternating grey
# table rows, Arial throughout.

NAVY = "#1f3864"
WHITE = "#ffffff"
LIGHT_GREY = "#f2f2f2"
DARK_GREY = "#555555"
GREEN = "#2e7d32"
RED = "#c62828"

FONT_FAMILY = "Arial"


def setup_styles(root):
    """Configures a consistent ttk theme across the whole application.
    Call this once, right after creating the root window."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")  # the built-in theme most willing to take colour overrides
    except tk.TclError:
        pass

    root.configure(bg=WHITE)

    style.configure("TFrame", background=WHITE)
    style.configure("TLabel", background=WHITE, font=(FONT_FAMILY, 10))

    style.configure("Header.TLabel", background=NAVY, foreground=WHITE,
                    font=(FONT_FAMILY, 16, "bold"))
    style.configure("SubHeader.TLabel", background=WHITE, foreground=NAVY,
                    font=(FONT_FAMILY, 11, "bold"))
    style.configure("Status.TLabel", background=LIGHT_GREY, foreground=DARK_GREY,
                    font=(FONT_FAMILY, 9))
    style.configure("Valid.TLabel", background=WHITE, foreground=GREEN, font=(FONT_FAMILY, 9))
    style.configure("Invalid.TLabel", background=WHITE, foreground=RED, font=(FONT_FAMILY, 9))

    style.configure("TButton", font=(FONT_FAMILY, 10), padding=6)
    style.configure("Primary.TButton", font=(FONT_FAMILY, 10, "bold"))
    style.map("Primary.TButton",
              background=[("!disabled", NAVY)],
              foreground=[("!disabled", WHITE)])

    style.configure("TNotebook", background=WHITE, tabmargins=[2, 5, 2, 0])
    style.configure("TNotebook.Tab", font=(FONT_FAMILY, 10), padding=[16, 8])
    style.map("TNotebook.Tab",
              background=[("selected", NAVY), ("!selected", LIGHT_GREY)],
              foreground=[("selected", WHITE), ("!selected", "#222222")])

    style.configure("Treeview", font=(FONT_FAMILY, 10), rowheight=26,
                    background=WHITE, fieldbackground=WHITE)
    style.configure("Treeview.Heading", font=(FONT_FAMILY, 10, "bold"),
                    background=NAVY, foreground=WHITE)
    style.map("Treeview.Heading", background=[("active", NAVY)])

    style.configure("TEntry", padding=4)
    style.configure("TCombobox", padding=4)

    return style


def build_header_bar(parent, title_text):
    """Navy title bar shown at the top of the login screen and the main
    dashboard, matching the header treatment in the detailed designs."""
    bar = tk.Frame(parent, bg=NAVY)
    ttk.Label(bar, text=title_text, style="Header.TLabel").pack(
        side="left", padx=16, pady=12
    )
    return bar


def stripe_treeview(tree: ttk.Treeview):
    """Applies alternating light-grey row colouring to a Treeview's existing
    rows. Call this again any time rows are inserted/removed, since the
    stripe pattern is just a tag applied per-row, not automatic."""
    tree.tag_configure("oddrow", background=WHITE)
    tree.tag_configure("evenrow", background=LIGHT_GREY)
    for index, item in enumerate(tree.get_children("")):
        tree.item(item, tags=("evenrow" if index % 2 == 0 else "oddrow",))


def make_striped_treeview(parent, columns, headings, widths=None):
    """
    Builds a ttk.Treeview set up as a table: no visible tree column, just
    the given data columns, headings, and striped rows. Returns the
    Treeview - caller is responsible for calling stripe_treeview(tree)
    again after inserting/removing rows.
    """
    tree = ttk.Treeview(parent, columns=columns, show="headings")
    for i, col in enumerate(columns):
        tree.heading(col, text=headings[i])
        width = widths[i] if widths else 120
        tree.column(col, width=width, anchor="w")
    return tree


def show_status_bar(parent, status_text_var):
    """Light-grey status bar shown at the bottom of the main dashboard,
    bound to a StringVar so callers can update it just by setting the var."""
    bar = tk.Frame(parent, bg=LIGHT_GREY)
    ttk.Label(bar, textvariable=status_text_var, style="Status.TLabel").pack(
        side="left", padx=8, pady=4
    )
    return bar


class ScrollableFrame(ttk.Frame):
    """A frame that can be scrolled with the scrollbar or the mouse wheel.
    Needed because the Roll Call list can have 100+ rows in it, which
    doesn't fit in the window at once.

    Usage: put widgets inside `self.inner` (not `self` directly).
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)

        self.inner.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel support - only while the pointer is over this canvas,
        # otherwise scrolling here would also scroll other tabs.
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", self._on_mousewheel(canvas)))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    @staticmethod
    def _on_mousewheel(canvas):
        def handler(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return handler


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Netball Trial Management System")
        self.geometry("900x600")

        setup_styles(self)

        database.init_db()
        # Contingency plan for database corruption (SAT risk register) -
        # a dated copy before anything this session could touch it.
        database.backup_database()

        self.current_user = None
        self.selected_trial_id = None
        self.attendance_vars = {}  # player_id -> IntVar, used on the Roll Call tab
        self.status_var = tk.StringVar(value="No trial selected")

        self.build_login_screen()

    # ----------------------------------------------------------------- #
    # Login
    # ----------------------------------------------------------------- #

    def build_login_screen(self):
        build_header_bar(self, "Netball Trial Management System").pack(fill="x")

        self.login_frame = ttk.Frame(self)
        self.login_frame.pack(expand=True)

        ttk.Label(self.login_frame, text="Username").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.login_username_entry = ttk.Entry(self.login_frame)
        self.login_username_entry.grid(row=1, column=1, pady=5)

        ttk.Label(self.login_frame, text="Password").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.login_password_entry = ttk.Entry(self.login_frame, show="*")
        self.login_password_entry.grid(row=2, column=1, pady=5)

        ttk.Label(self.login_frame, text="Role").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.login_role_combo = ttk.Combobox(
            self.login_frame, values=list(VALID_ROLES), state="readonly"
        )
        self.login_role_combo.set("coordinator")
        self.login_role_combo.grid(row=3, column=1, pady=5)

        ttk.Button(
            self.login_frame, text="Log In", style="Primary.TButton", command=self.attempt_login
        ).grid(row=4, column=0, columnspan=2, pady=15)

        self.login_error_label = ttk.Label(self.login_frame, text="", style="Invalid.TLabel")
        self.login_error_label.grid(row=5, column=0, columnspan=2)

        # First-run help - the default account until a signup screen exists.
        ttk.Label(
            self.login_frame,
            text="First run? Default login is coordinator / coordinator123",
            style="Status.TLabel",
        ).grid(row=6, column=0, columnspan=2, pady=(10, 0))

    def attempt_login(self):
        username = self.login_username_entry.get().strip()
        password = self.login_password_entry.get()
        role = self.login_role_combo.get()

        if not username or not password or not role:
            self.login_error_label.configure(text="All fields are required.")
            return

        user = login(username, password, role)
        if not user:
            # Deliberately vague - see login()'s docstring for why.
            self.login_error_label.configure(text="Incorrect username, password, or role.")
            self.login_password_entry.delete(0, "end")
            return

        self.current_user = user
        for widget in self.winfo_children():
            widget.destroy()
        self.build_main_app()

    def log_out(self):
        for widget in self.winfo_children():
            widget.destroy()

        # Clear out widget references from the previous session - without
        # this, logging in as a role with fewer tabs (e.g. coach after a
        # coordinator session) would leave stale attributes like
        # self.players_list pointing at an already-destroyed widget, and
        # select_trial()'s hasattr() checks would wrongly think that tab
        # still exists and crash trying to use it.
        stale_attrs = [
            "trials_tab", "players_tab", "roll_call_tab", "rounds_tab", "export_tab",
            "trials_tree", "players_tree", "roll_call_frame", "round_nav_label",
            "rounds_content", "trial_picker_combo",
        ]
        for attr in stale_attrs:
            if hasattr(self, attr):
                delattr(self, attr)

        self.current_user = None
        self.selected_trial_id = None
        self.attendance_vars = {}
        self.status_var.set("No trial selected")
        self.build_login_screen()

    # ----------------------------------------------------------------- #
    # Main app (built after a successful login)
    # ----------------------------------------------------------------- #

    def build_main_app(self):
        build_header_bar(self, "Netball Trial Management System").pack(fill="x")

        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(
            top_bar,
            text=f"Logged in: {self.current_user.username} ({self.current_user.display_role()})",
            style="SubHeader.TLabel",
        ).pack(side="left")
        ttk.Button(top_bar, text="Log Out", command=self.log_out).pack(side="right")

        # Coordinators pick their active trial from the list on the Trials
        # tab. Everyone else doesn't get that tab, so they need some other
        # way to say which trial they're working with - a simple dropdown
        # here does the job for now.
        if not self.current_user.has_access("Trials"):
            picker = ttk.Frame(self)
            picker.pack(fill="x", padx=10, pady=5)
            ttk.Label(picker, text="Trial:").pack(side="left")
            self.trial_picker_var = tk.StringVar()
            self.trial_picker_combo = ttk.Combobox(
                picker, textvariable=self.trial_picker_var, state="readonly", width=40
            )
            self.trial_picker_combo.pack(side="left", padx=5)
            self.trial_picker_combo.bind("<<ComboboxSelected>>", self.on_trial_picker_selected)
            self._trial_picker_options = database.get_all_trials()
            self.trial_picker_combo["values"] = [
                f"{t['trial_id']} - {t['trial_name']} ({t['age_group']})"
                for t in self._trial_picker_options
            ]

        # Status bar goes at the bottom, packed BEFORE the notebook (below)
        # so it stays pinned to the bottom edge and the notebook fills
        # whatever vertical space is left over.
        show_status_bar(self, self.status_var).pack(fill="x", side="bottom")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        # Only build/add a tab if the logged-in role is actually allowed to
        # see it (FR12). tab_name here must match the keys used in
        # ROLE_PERMISSIONS.
        tab_definitions = [
            ("Trials", "trials_tab", self.build_trials_tab),
            ("Players", "players_tab", self.build_players_tab),
            ("Roll Call", "roll_call_tab", self.build_roll_call_tab),
            ("Rounds", "rounds_tab", self.build_rounds_tab),
            ("Export", "export_tab", self.build_export_tab),
        ]

        for tab_name, attr_name, build_method in tab_definitions:
            if not self.current_user.has_access(tab_name):
                continue
            frame = ttk.Frame(notebook)
            setattr(self, attr_name, frame)
            notebook.add(frame, text=tab_name)
            build_method()

    def on_trial_picker_selected(self, event):
        index = self.trial_picker_combo.current()
        if index < 0:
            return
        trial = self._trial_picker_options[index]
        self.select_trial(trial["trial_id"])

    # ----------------------------------------------------------------- #
    # Trials tab
    # ----------------------------------------------------------------- #

    def build_trials_tab(self):
        form = ttk.Frame(self.trials_tab)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Label(form, text="Trial Name").grid(row=0, column=0, sticky="w")
        self.trial_name_entry = ttk.Entry(form)
        self.trial_name_entry.grid(row=0, column=1, padx=5)

        ttk.Label(form, text="Age Group").grid(row=1, column=0, sticky="w")
        self.age_group_entry = ttk.Entry(form)
        self.age_group_entry.grid(row=1, column=1, padx=5)

        ttk.Label(form, text="Date (DD/MM/YYYY)").grid(row=2, column=0, sticky="w")
        self.trial_date_entry = ttk.Entry(form)
        self.trial_date_entry.grid(row=2, column=1, padx=5)

        ttk.Label(form, text="Courts").grid(row=3, column=0, sticky="w")
        self.num_courts_var = tk.IntVar(value=1)
        courts_frame = ttk.Frame(form)
        courts_frame.grid(row=3, column=1, sticky="w")
        ttk.Radiobutton(courts_frame, text="1 court", variable=self.num_courts_var, value=1).pack(side="left")
        ttk.Radiobutton(courts_frame, text="2 courts", variable=self.num_courts_var, value=2).pack(side="left")

        # Optional (FR3) - if left blank, DOB just isn't checked against an
        # age window for this trial. Filling both in enables the live
        # green/red validation on the Players tab registration form.
        ttk.Label(form, text="Birth Year Range (optional)").grid(row=4, column=0, sticky="w")
        birth_year_frame = ttk.Frame(form)
        birth_year_frame.grid(row=4, column=1, sticky="w")
        self.min_birth_year_entry = ttk.Entry(birth_year_frame, width=8)
        self.min_birth_year_entry.pack(side="left")
        ttk.Label(birth_year_frame, text=" to ").pack(side="left")
        self.max_birth_year_entry = ttk.Entry(birth_year_frame, width=8)
        self.max_birth_year_entry.pack(side="left")

        ttk.Button(form, text="Create Trial", style="Primary.TButton", command=self.create_trial).grid(
            row=5, column=0, columnspan=2, pady=10
        )

        # Tabular trial list (Criteria 5, dashboard mockup) - a table with
        # sortable columns is more useful than a bare list once a
        # coordinator has several trials on the go at once.
        self.trials_tree = make_striped_treeview(
            self.trials_tab,
            columns=("name", "age_group", "date", "courts"),
            headings=["Trial Name", "Age Group", "Date", "Courts"],
            widths=[220, 100, 110, 80],
        )
        self.trials_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.trials_tree.bind("<<TreeviewSelect>>", self.on_select_trial)

        self.refresh_trials_list()

    def create_trial(self):
        name = self.trial_name_entry.get().strip()
        age_group = self.age_group_entry.get().strip()
        date = self.trial_date_entry.get().strip()
        num_courts = self.num_courts_var.get()
        min_year_text = self.min_birth_year_entry.get().strip()
        max_year_text = self.max_birth_year_entry.get().strip()

        if not name or not age_group or not date:
            messagebox.showerror("Error", "All fields are required.")
            return

        # Birth years are optional, but if either is given both must be
        # given and both must actually be numbers - half a range isn't
        # useful for FR3's eligibility check.
        min_birth_year = max_birth_year = None
        if min_year_text or max_year_text:
            if not (min_year_text.isdigit() and max_year_text.isdigit()):
                messagebox.showerror("Error", "Birth years must be whole numbers, e.g. 2013.")
                return
            min_birth_year, max_birth_year = int(min_year_text), int(max_year_text)
            if min_birth_year > max_birth_year:
                messagebox.showerror("Error", "Minimum birth year can't be after the maximum.")
                return

        database.create_trial(name, age_group, date, num_courts, min_birth_year, max_birth_year)
        self.trial_name_entry.delete(0, "end")
        self.age_group_entry.delete(0, "end")
        self.trial_date_entry.delete(0, "end")
        self.min_birth_year_entry.delete(0, "end")
        self.max_birth_year_entry.delete(0, "end")
        self.num_courts_var.set(1)
        self.refresh_trials_list()

    def refresh_trials_list(self):
        self.trials_tree.delete(*self.trials_tree.get_children())
        for t in database.get_all_trials():
            courts_text = f"{t['num_courts']} court{'s' if t['num_courts'] > 1 else ''}"
            self.trials_tree.insert(
                "", "end", iid=str(t["trial_id"]),
                values=(t["trial_name"], t["age_group"], t["trial_date"], courts_text),
            )
        stripe_treeview(self.trials_tree)

    def on_select_trial(self, event):
        selection = self.trials_tree.selection()
        if not selection:
            return
        self.select_trial(int(selection[0]))

    def select_trial(self, trial_id):
        """Sets the active trial and refreshes whichever tabs the current
        role actually has (a coach/referee won't have players_tree etc,
        since they don't get the Players tab)."""
        self.selected_trial_id = trial_id
        trial = database.get_trial(trial_id)
        if trial:
            self.status_var.set(
                f"Trial: {trial['trial_name']} ({trial['age_group']}) - "
                f"{trial['num_courts']} court{'s' if trial['num_courts'] > 1 else ''}"
            )
        if hasattr(self, "players_tree"):
            self.refresh_players_list()
        if hasattr(self, "roll_call_frame"):
            self.refresh_roll_call()
        if hasattr(self, "rounds_display"):
            self.refresh_rounds_display()

    # ----------------------------------------------------------------- #
    # Players tab
    # ----------------------------------------------------------------- #

    def build_players_tab(self):
        form = ttk.Frame(self.players_tab)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Label(form, text="First Name").grid(row=0, column=0, sticky="w")
        self.first_name_entry = ttk.Entry(form)
        self.first_name_entry.grid(row=0, column=1, padx=5)

        ttk.Label(form, text="Last Name").grid(row=1, column=0, sticky="w")
        self.last_name_entry = ttk.Entry(form)
        self.last_name_entry.grid(row=1, column=1, padx=5)

        ttk.Label(form, text="DOB (DD/MM/YYYY)").grid(row=2, column=0, sticky="w")
        self.dob_entry = ttk.Entry(form)
        self.dob_entry.grid(row=2, column=1, padx=5)
        self.dob_entry.bind("<KeyRelease>", self.on_dob_typed)

        # FR3 - live feedback as the coordinator types, matching the "✓
        # Valid for U13" annotation in the detailed designs. This is
        # informational only and never blocks registration - a permit
        # might apply, so the coordinator has the final call.
        self.dob_validation_label = ttk.Label(form, text="", style="Valid.TLabel")
        self.dob_validation_label.grid(row=2, column=2, sticky="w", padx=5)

        ttk.Label(form, text="Position 1").grid(row=3, column=0, sticky="w")
        self.pos1_combo = ttk.Combobox(form, values=POSITIONS, state="readonly")
        self.pos1_combo.grid(row=3, column=1, padx=5)

        ttk.Label(form, text="Position 2").grid(row=4, column=0, sticky="w")
        self.pos2_combo = ttk.Combobox(form, values=POSITIONS, state="readonly")
        self.pos2_combo.grid(row=4, column=1, padx=5)

        ttk.Button(
            form, text="Register Player", style="Primary.TButton", command=self.create_player
        ).grid(row=5, column=0, columnspan=2, pady=10)

        self.players_tree = make_striped_treeview(
            self.players_tab,
            columns=("trial_no", "name", "dob", "pos1", "pos2"),
            headings=["#", "Name", "DOB", "Pos 1", "Pos 2"],
            widths=[40, 200, 100, 70, 70],
        )
        self.players_tree.pack(fill="both", expand=True, padx=10, pady=10)

    def on_dob_typed(self, event=None):
        """Live FR3 feedback - checks the DOB typed so far against the
        selected trial's birth year window and shows a green tick or red
        warning. Never blocks anything; create_player() only checks the
        date FORMAT, not eligibility, since a permit can override this."""
        dob = self.dob_entry.get().strip()
        if not dob:
            self.dob_validation_label.configure(text="")
            return
        if not self.selected_trial_id:
            self.dob_validation_label.configure(text="")
            return

        trial = database.get_trial(self.selected_trial_id)
        if not database.is_valid_date(dob):
            # Don't show "invalid format" on every half-typed keystroke -
            # only once it's plausibly a complete date.
            if len(dob) >= 10:
                self.dob_validation_label.configure(text="Invalid date format", style="Invalid.TLabel")
            else:
                self.dob_validation_label.configure(text="")
            return

        is_valid, message = database.check_dob_eligibility(
            dob, trial.get("min_birth_year"), trial.get("max_birth_year")
        )
        self.dob_validation_label.configure(
            text=message, style="Valid.TLabel" if is_valid else "Invalid.TLabel"
        )

    def create_player(self):
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        first_name = self.first_name_entry.get().strip()
        last_name = self.last_name_entry.get().strip()
        dob = self.dob_entry.get().strip()
        pos1 = self.pos1_combo.get()
        pos2 = self.pos2_combo.get()

        if not first_name or not last_name or not dob or not pos1 or not pos2:
            messagebox.showerror("Error", "All fields are required.")
            return

        if not database.is_valid_date(dob):
            messagebox.showerror("Error", "DOB must be in DD/MM/YYYY format.")
            return

        trial_number = database.create_player(
            self.selected_trial_id, first_name, last_name, dob, pos1, pos2
        )

        self.first_name_entry.delete(0, "end")
        self.last_name_entry.delete(0, "end")
        self.dob_entry.delete(0, "end")
        self.dob_validation_label.configure(text="")
        self.pos1_combo.set("")
        self.pos2_combo.set("")

        messagebox.showinfo("Registered", f"Player registered. Trial number: {trial_number}")

        self.refresh_players_list()
        self.refresh_roll_call()

    def refresh_players_list(self):
        self.players_tree.delete(*self.players_tree.get_children())
        if not self.selected_trial_id:
            return
        players = database.get_players_for_trial(self.selected_trial_id)
        for p in players:
            self.players_tree.insert(
                "", "end", iid=str(p["player_id"]),
                values=(
                    f"#{p['trial_number']}",
                    f"{p['first_name']} {p['last_name']}",
                    p["dob"],
                    p["position_1"],
                    p["position_2"],
                ),
            )
        stripe_treeview(self.players_tree)

    # ----------------------------------------------------------------- #
    # Roll Call tab
    # ----------------------------------------------------------------- #

    def build_roll_call_tab(self):
        ttk.Label(
            self.roll_call_tab, text="Tick each player who is present for this trial:"
        ).pack(anchor="w", padx=10, pady=(10, 0))

        buttons_frame = ttk.Frame(self.roll_call_tab)
        buttons_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(buttons_frame, text="Select All", command=self.select_all_present).pack(side="left")
        ttk.Button(buttons_frame, text="Clear All", command=self.clear_all_present).pack(side="left", padx=5)

        # Scrollable area - a plain Frame packed with 100 checkbuttons just
        # runs off the bottom of the window, so this wraps it in a canvas.
        self.roll_call_scroll = ScrollableFrame(self.roll_call_tab)
        self.roll_call_scroll.pack(fill="both", expand=True, padx=10, pady=5)
        self.roll_call_frame = self.roll_call_scroll.inner

        ttk.Button(
            self.roll_call_tab, text="Confirm Roll Call", style="Primary.TButton",
            command=self.confirm_roll_call
        ).pack(pady=10)

    def refresh_roll_call(self):
        for widget in self.roll_call_frame.winfo_children():
            widget.destroy()
        self.attendance_vars = {}

        if not self.selected_trial_id:
            return

        players = database.get_players_for_trial(self.selected_trial_id)
        existing = database.get_attendance_map(self.selected_trial_id)

        for p in players:
            var = tk.IntVar(value=existing.get(p["player_id"], 0))
            self.attendance_vars[p["player_id"]] = var
            ttk.Checkbutton(
                self.roll_call_frame,
                text=f"#{p['trial_number']} {p['first_name']} {p['last_name']}",
                variable=var,
            ).pack(anchor="w")

    def select_all_present(self):
        for var in self.attendance_vars.values():
            var.set(1)

    def clear_all_present(self):
        for var in self.attendance_vars.values():
            var.set(0)

    def confirm_roll_call(self):
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        for player_id, var in self.attendance_vars.items():
            database.set_attendance(player_id, self.selected_trial_id, bool(var.get()))

        present_count = sum(1 for var in self.attendance_vars.values() if var.get())
        messagebox.showinfo("Roll Call Saved", f"{present_count} players marked present.")

    # ----------------------------------------------------------------- #
    # Rounds tab
    # ----------------------------------------------------------------- #

    def build_rounds_tab(self):
        form = ttk.Frame(self.rounds_tab)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Button(
            form, text="Generate Rounds", style="Primary.TButton", command=self.generate_rounds
        ).pack(side="left")

        ttk.Label(
            self.rounds_tab,
            text="Automatically generates the fewest rounds needed so every present player "
                 "gets at least one game in their 1st preference and one in their 2nd "
                 "preference position. Courts are set on the Trials tab.",
        ).pack(anchor="w", padx=10)

        # Round navigator - one round shown at a time, matching the trial
        # sheet mockup's Prev/Next round arrows, rather than dumping every
        # round's text one after another.
        nav = ttk.Frame(self.rounds_tab)
        nav.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Button(nav, text="\u25c0 Prev Round", command=self.prev_round).pack(side="left")
        self.round_nav_label = ttk.Label(nav, text="No rounds generated yet", style="SubHeader.TLabel")
        self.round_nav_label.pack(side="left", padx=15)
        ttk.Button(nav, text="Next Round \u25b6", command=self.next_round).pack(side="left")

        # Scrollable area holding the court/team tables for whichever round
        # is currently selected - 2 courts x 2 teams x 7 rows can run
        # taller than the window on smaller screens.
        self.rounds_scroll = ScrollableFrame(self.rounds_tab)
        self.rounds_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        self.rounds_content = self.rounds_scroll.inner

        self.current_round_number = None
        self._rounds_by_number = {}  # {round_number: {court_number: {team: round_row}}}

    def generate_rounds(self):
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        trial = database.get_trial(self.selected_trial_id)
        num_courts = trial["num_courts"]

        present_players = database.get_present_players(self.selected_trial_id)

        try:
            rounds_output, rounds_used, failed = algorithm.generate_minimum_rounds(
                present_players, num_courts
            )
        except ValueError as e:
            messagebox.showerror("Cannot Generate Rounds", str(e))
            return

        # Wipe any previous draw for this trial, then save the new one.
        database.clear_rounds_for_trial(self.selected_trial_id)

        for round_data in rounds_output:
            bib_colour = algorithm.COURT_BIB_COLOURS[round_data["court_number"]][round_data["team"]]
            round_id = database.create_round_entry(
                self.selected_trial_id,
                round_data["round_number"],
                round_data["court_number"],
                round_data["team"],
                bib_colour,
            )
            for assignment in round_data["assignments"]:
                database.create_assignment(round_id, assignment["player_id"], assignment["position"])

        if failed:
            messagebox.showwarning(
                "Guarantee Not Fully Met",
                f"Hit the {algorithm.MAX_ROUNDS} round safety cap and {len(failed)} player(s) "
                f"still didn't get both preferred positions. The algorithm may need a rethink "
                f"for this roster size.",
            )
        else:
            messagebox.showinfo(
                "Rounds Generated", f"Generated the minimum needed: {rounds_used} round(s)."
            )

        # A fresh draw always starts the navigator back at round 1.
        self.current_round_number = None
        self.refresh_rounds_display()

    def refresh_rounds_display(self):
        """Rebuilds the round_number -> court_number -> team lookup from the
        database, then renders whichever round is currently selected (or
        round 1, on a fresh generate)."""
        self._rounds_by_number = {}
        if self.selected_trial_id:
            for r in database.get_rounds_for_trial(self.selected_trial_id):
                self._rounds_by_number.setdefault(r["round_number"], {}) \
                    .setdefault(r["court_number"], {})[r["team"]] = r

        round_numbers = sorted(self._rounds_by_number.keys())
        if not round_numbers:
            self.current_round_number = None
            self.round_nav_label.configure(text="No rounds generated yet")
            for widget in self.rounds_content.winfo_children():
                widget.destroy()
            return

        if self.current_round_number not in round_numbers:
            self.current_round_number = round_numbers[0]
        self.render_round(self.current_round_number)

    def render_round(self, round_number):
        """Draws one round: a heading, then each court stacked vertically,
        with that court's two teams side by side as separate tables - this
        is what actually matches the trial sheet mockup's layout, instead
        of one long scrolling wall of text."""
        round_numbers = sorted(self._rounds_by_number.keys())
        self.current_round_number = round_number
        self.round_nav_label.configure(text=f"Round {round_number} of {round_numbers[-1]}")

        for widget in self.rounds_content.winfo_children():
            widget.destroy()

        courts = self._rounds_by_number[round_number]
        for court_number in sorted(courts.keys()):
            ttk.Label(
                self.rounds_content, text=f"Court {court_number}", style="SubHeader.TLabel"
            ).pack(anchor="w", pady=(14 if court_number > 1 else 0, 6))

            teams_row = ttk.Frame(self.rounds_content)
            teams_row.pack(fill="x")

            for team in ("A", "B"):
                round_row = courts[court_number].get(team)
                if not round_row:
                    continue

                team_block = ttk.Frame(teams_row)
                team_block.pack(side="left", padx=(0, 24), anchor="n")

                ttk.Label(team_block, text=f"Team {team}", style="SubHeader.TLabel").pack(anchor="w")
                ttk.Label(
                    team_block, text=f"Bib Colour: {round_row['bib_colour']}", style="Status.TLabel"
                ).pack(anchor="w", pady=(0, 6))

                tree = make_striped_treeview(
                    team_block,
                    columns=("position", "player", "number"),
                    headings=["Position", "Player", "Number"],
                    widths=[70, 170, 70],
                )
                tree.pack()

                assignments = database.get_assignments_for_round(round_row["round_id"])
                # Standard netball court order, matching the paper game sheets.
                assignments.sort(key=lambda a: POSITIONS.index(a["position"]))
                for a in assignments:
                    tree.insert(
                        "", "end",
                        values=(a["position"], f"{a['first_name']} {a['last_name']}", a["trial_number"]),
                    )
                stripe_treeview(tree)

    def prev_round(self):
        round_numbers = sorted(self._rounds_by_number.keys())
        if not round_numbers or self.current_round_number is None:
            return
        index = round_numbers.index(self.current_round_number)
        if index > 0:
            self.render_round(round_numbers[index - 1])

    def next_round(self):
        round_numbers = sorted(self._rounds_by_number.keys())
        if not round_numbers or self.current_round_number is None:
            return
        index = round_numbers.index(self.current_round_number)
        if index < len(round_numbers) - 1:
            self.render_round(round_numbers[index + 1])

    # ----------------------------------------------------------------- #
    # Export tab
    # ----------------------------------------------------------------- #

    def build_export_tab(self):
        ttk.Label(
            self.export_tab,
            text="Exports the full player register for the selected trial as a clean CSV file.",
        ).pack(anchor="w", padx=10, pady=10)

        ttk.Button(
            self.export_tab, text="Export Players to CSV", style="Primary.TButton",
            command=self.export_players_csv
        ).pack(anchor="w", padx=10)

        ttk.Separator(self.export_tab, orient="horizontal").pack(fill="x", padx=10, pady=15)

        ttk.Label(
            self.export_tab,
            text="A dated backup is taken automatically every time the app starts. "
                 "You can also trigger one right now:",
        ).pack(anchor="w", padx=10)
        ttk.Button(
            self.export_tab, text="Back Up Database Now", command=self.backup_database_now
        ).pack(anchor="w", padx=10, pady=(5, 0))

    def export_players_csv(self):
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        players = database.get_players_for_trial(self.selected_trial_id)
        if not players:
            messagebox.showerror("Error", "This trial has no registered players yet.")
            return

        trial = database.get_trial(self.selected_trial_id)
        default_name = f"{trial['trial_name'].replace(' ', '_')}_players.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv")],
        )
        if not filepath:
            return  # coordinator cancelled the save dialog

        database.export_players_csv(players, filepath)
        messagebox.showinfo("Export Complete", f"Player list exported to:\n{filepath}")

    def backup_database_now(self):
        backup_path = database.backup_database()
        if backup_path:
            messagebox.showinfo("Backup Complete", f"Database backed up to:\n{backup_path}")
        else:
            messagebox.showerror("Backup Failed", "No database file was found to back up.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
