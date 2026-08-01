"""
main.py

Added since last commit:
    - Roll Call tab is now scrollable (it was unusable once you had 100
      players - the checkbox list just ran off the bottom of the window)
    - "Select All" / "Clear All" buttons on the Roll Call tab
    - number of courts (1 or 2) is now chosen when the trial is created,
      not on the Rounds tab
    - Rounds tab no longer asks the coordinator to guess a round count -
      it calls algorithm.generate_minimum_rounds() and just works out the
      fewest rounds needed to guarantee everyone gets both their preferred
      positions at least once
"""

import tkinter as tk
from tkinter import ttk, messagebox

import database
import algorithm

POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]


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
        self.geometry("850x550")

        database.init_db()

        self.selected_trial_id = None
        self.attendance_vars = {}  # player_id -> IntVar, used on the Roll Call tab

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.trials_tab = ttk.Frame(notebook)
        self.players_tab = ttk.Frame(notebook)
        self.roll_call_tab = ttk.Frame(notebook)
        self.rounds_tab = ttk.Frame(notebook)

        notebook.add(self.trials_tab, text="Trials")
        notebook.add(self.players_tab, text="Players")
        notebook.add(self.roll_call_tab, text="Roll Call")
        notebook.add(self.rounds_tab, text="Rounds")

        self.build_trials_tab()
        self.build_players_tab()
        self.build_roll_call_tab()
        self.build_rounds_tab()

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

        ttk.Button(form, text="Create Trial", command=self.create_trial).grid(
            row=4, column=0, columnspan=2, pady=10
        )

        self.trials_list = tk.Listbox(self.trials_tab)
        self.trials_list.pack(fill="both", expand=True, padx=10, pady=10)
        self.trials_list.bind("<<ListboxSelect>>", self.on_select_trial)

        self.refresh_trials_list()

    def create_trial(self):
        name = self.trial_name_entry.get().strip()
        age_group = self.age_group_entry.get().strip()
        date = self.trial_date_entry.get().strip()
        num_courts = self.num_courts_var.get()

        if not name or not age_group or not date:
            messagebox.showerror("Error", "All fields are required.")
            return

        database.create_trial(name, age_group, date, num_courts)
        self.trial_name_entry.delete(0, "end")
        self.age_group_entry.delete(0, "end")
        self.trial_date_entry.delete(0, "end")
        self.num_courts_var.set(1)
        self.refresh_trials_list()

    def refresh_trials_list(self):
        self.trials_list.delete(0, "end")
        self.trials = database.get_all_trials()
        for t in self.trials:
            self.trials_list.insert(
                "end",
                f"{t['trial_id']} - {t['trial_name']} ({t['age_group']}) - "
                f"{t['num_courts']} court{'s' if t['num_courts'] > 1 else ''}",
            )

    def on_select_trial(self, event):
        selection = self.trials_list.curselection()
        if not selection:
            return
        trial = self.trials[selection[0]]
        self.selected_trial_id = trial["trial_id"]
        self.refresh_players_list()
        self.refresh_roll_call()
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

        ttk.Label(form, text="Position 1").grid(row=3, column=0, sticky="w")
        self.pos1_combo = ttk.Combobox(form, values=POSITIONS, state="readonly")
        self.pos1_combo.grid(row=3, column=1, padx=5)

        ttk.Label(form, text="Position 2").grid(row=4, column=0, sticky="w")
        self.pos2_combo = ttk.Combobox(form, values=POSITIONS, state="readonly")
        self.pos2_combo.grid(row=4, column=1, padx=5)

        ttk.Button(form, text="Register Player", command=self.create_player).grid(
            row=5, column=0, columnspan=2, pady=10
        )

        self.players_list = tk.Listbox(self.players_tab)
        self.players_list.pack(fill="both", expand=True, padx=10, pady=10)

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
        self.pos1_combo.set("")
        self.pos2_combo.set("")

        messagebox.showinfo("Registered", f"Player registered. Trial number: {trial_number}")

        self.refresh_players_list()
        self.refresh_roll_call()

    def refresh_players_list(self):
        self.players_list.delete(0, "end")
        if not self.selected_trial_id:
            return
        players = database.get_players_for_trial(self.selected_trial_id)
        for p in players:
            self.players_list.insert(
                "end",
                f"#{p['trial_number']} {p['first_name']} {p['last_name']} - "
                f"{p['position_1']}/{p['position_2']}",
            )

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
            self.roll_call_tab, text="Confirm Roll Call", command=self.confirm_roll_call
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

        ttk.Button(form, text="Generate Rounds", command=self.generate_rounds).pack(side="left")

        ttk.Label(
            self.rounds_tab,
            text="Automatically generates the fewest rounds needed so every present player "
                 "gets at least one game in their 1st preference and one in their 2nd "
                 "preference position. Courts are set on the Trials tab.",
        ).pack(anchor="w", padx=10)

        self.rounds_display = tk.Text(self.rounds_tab, height=25, width=90)
        self.rounds_display.pack(fill="both", expand=True, padx=10, pady=10)

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

        self.refresh_rounds_display()

    def refresh_rounds_display(self):
        self.rounds_display.delete("1.0", "end")
        if not self.selected_trial_id:
            return

        rounds = database.get_rounds_for_trial(self.selected_trial_id)
        for round_row in rounds:
            self.rounds_display.insert(
                "end",
                f"\nRound {round_row['round_number']} - Court {round_row['court_number']} - "
                f"Team {round_row['team']} ({round_row['bib_colour']})\n",
            )
            assignments = database.get_assignments_for_round(round_row["round_id"])
            # Keep them in standard netball court order for readability.
            assignments.sort(key=lambda a: POSITIONS.index(a["position"]))
            for a in assignments:
                self.rounds_display.insert(
                    "end",
                    f"   {a['position']}: #{a['trial_number']} {a['first_name']} {a['last_name']}\n",
                )


if __name__ == "__main__":
    app = App()
    app.mainloop()


# --------------------------------------------------------------------------- #
# main.py v1.3
# --------------------------------------------------------------------------- #
