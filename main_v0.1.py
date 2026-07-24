"""
main.py
First working version of the Netball Trial app window.

Just two tabs for now: Trials and Players. No login yet, no roll call,
no round generation. Just enough to create a trial and register players
against it to prove the data model works.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import database

POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Netball Trial Management System")
        self.geometry("800x500")

        database.init_db()

        self.selected_trial_id = None

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.trials_tab = ttk.Frame(notebook)
        self.players_tab = ttk.Frame(notebook)

        notebook.add(self.trials_tab, text="Trials")
        notebook.add(self.players_tab, text="Players")

        self.build_trials_tab()
        self.build_players_tab()

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

        ttk.Button(form, text="Create Trial", command=self.create_trial).grid(
            row=3, column=0, columnspan=2, pady=10
        )

        self.trials_list = tk.Listbox(self.trials_tab)
        self.trials_list.pack(fill="both", expand=True, padx=10, pady=10)
        self.trials_list.bind("<<ListboxSelect>>", self.on_select_trial)

        self.refresh_trials_list()

    def create_trial(self):
        name = self.trial_name_entry.get().strip()
        age_group = self.age_group_entry.get().strip()
        date = self.trial_date_entry.get().strip()

        if not name or not age_group or not date:
            messagebox.showerror("Error", "All fields are required.")
            return

        database.create_trial(name, age_group, date)
        self.trial_name_entry.delete(0, "end")
        self.age_group_entry.delete(0, "end")
        self.trial_date_entry.delete(0, "end")
        self.refresh_trials_list()

    def refresh_trials_list(self):
        self.trials_list.delete(0, "end")
        self.trials = database.get_all_trials()
        for t in self.trials:
            self.trials_list.insert("end", f"{t['trial_id']} - {t['trial_name']} ({t['age_group']})")

    def on_select_trial(self, event):
        selection = self.trials_list.curselection()
        if not selection:
            return
        trial = self.trials[selection[0]]
        self.selected_trial_id = trial["trial_id"]
        self.refresh_players_list()

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

        database.create_player(self.selected_trial_id, first_name, last_name, dob, pos1, pos2)

        self.first_name_entry.delete(0, "end")
        self.last_name_entry.delete(0, "end")
        self.dob_entry.delete(0, "end")
        self.pos1_combo.set("")
        self.pos2_combo.set("")

        self.refresh_players_list()

    def refresh_players_list(self):
        self.players_list.delete(0, "end")
        if not self.selected_trial_id:
            return
        players = database.get_players_for_trial(self.selected_trial_id)
        for p in players:
            self.players_list.insert(
                "end", f"{p['first_name']} {p['last_name']} - {p['position_1']}/{p['position_2']}"
            )


if __name__ == "__main__":
    app = App()
    app.mainloop()
