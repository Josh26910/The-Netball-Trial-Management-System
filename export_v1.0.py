"""
export.py v1.0

Clean CSV export of the player register for a trial (FR11). This was the
#1 complaint about the old spreadsheet system - merged cells and dash
placeholders for empty fields made the export unusable without 30+ minutes
of manual reformatting. This just writes a plain, well-formed CSV: one
header row, one row per player, no merged cells, no dash placeholders.

PDF export (FR10, trial sheets with a notes column) hasn't been built yet -
CSV was the simpler of the two so it's going first.
"""

import csv
import os

CSV_HEADERS = ["Trial No", "First Name", "Last Name", "DOB", "Position 1", "Position 2"]

PLAYER_FIELD_ORDER = ["trial_number", "first_name", "last_name", "dob", "position_1", "position_2"]


def export_players_csv(players, filepath):
    """
    Writes a clean CSV of player registrations.
    `players` is a list of dicts (as returned by database.get_players_for_trial).
    """
    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for p in players:
            row = [p.get(field, "") for field in PLAYER_FIELD_ORDER]
            writer.writerow(row)

    return filepath


# --------------------------------------------------------------------------- #
# export.py v1.0
# --------------------------------------------------------------------------- #
