"""
database.py

Added since last commit:
    - trials now store num_courts (1 or 2) at creation time, instead of it
      being picked later when generating rounds
    - rounds table now records which court a game was on
    - new get_trial() helper so other modules can look up a trial's
      num_courts without pulling the whole list
"""

import sqlite3
from datetime import datetime

DB_PATH = "netball_trials.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates the tables if they don't exist yet."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS trials (
            trial_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            trial_name TEXT NOT NULL,
            age_group  TEXT NOT NULL,
            trial_date TEXT NOT NULL,
            num_courts INTEGER NOT NULL DEFAULT 1 CHECK (num_courts IN (1, 2))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            trial_id     INTEGER NOT NULL,
            trial_number INTEGER NOT NULL,
            first_name   TEXT NOT NULL,
            last_name    TEXT NOT NULL,
            dob          TEXT NOT NULL,
            position_1   TEXT NOT NULL,
            position_2   TEXT NOT NULL,
            FOREIGN KEY (trial_id) REFERENCES trials(trial_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id     INTEGER NOT NULL,
            trial_id      INTEGER NOT NULL,
            is_present    INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            FOREIGN KEY (trial_id) REFERENCES trials(trial_id)
        )
    """)

    # rounds now records court_number (was single-court only before)
    c.execute("""
        CREATE TABLE IF NOT EXISTS rounds (
            round_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            trial_id     INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            court_number INTEGER NOT NULL DEFAULT 1,
            team         TEXT NOT NULL,
            bib_colour   TEXT NOT NULL,
            FOREIGN KEY (trial_id) REFERENCES trials(trial_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id      INTEGER NOT NULL,
            player_id     INTEGER NOT NULL,
            position      TEXT NOT NULL,
            FOREIGN KEY (round_id) REFERENCES rounds(round_id),
            FOREIGN KEY (player_id) REFERENCES players(player_id)
        )
    """)

    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def is_valid_date(date_str):
    """Expects DD/MM/YYYY. Used before a player gets written to the DB."""
    try:
        datetime.strptime(date_str.strip(), "%d/%m/%Y")
        return True
    except (ValueError, AttributeError):
        return False


# --------------------------------------------------------------------------- #
# Trials
# --------------------------------------------------------------------------- #

def create_trial(trial_name, age_group, trial_date, num_courts=1):
    conn = get_connection()
    conn.execute(
        """INSERT INTO trials (trial_name, age_group, trial_date, num_courts)
           VALUES (?, ?, ?, ?)""",
        (trial_name, age_group, trial_date, num_courts),
    )
    conn.commit()
    conn.close()


def get_all_trials():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM trials ORDER BY trial_date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trial(trial_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM trials WHERE trial_id = ?", (trial_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# --------------------------------------------------------------------------- #
# Players
# --------------------------------------------------------------------------- #

def get_next_trial_number(trial_id):
    """Works out the next leg number for a new player in this trial."""
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(trial_number) AS m FROM players WHERE trial_id = ?", (trial_id,)
    ).fetchone()
    conn.close()
    return (row["m"] or 0) + 1


def create_player(trial_id, first_name, last_name, dob, position_1, position_2):
    trial_number = get_next_trial_number(trial_id)
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (trial_id, trial_number, first_name, last_name, dob,
                                 position_1, position_2)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (trial_id, trial_number, first_name, last_name, dob, position_1, position_2),
    )
    conn.commit()
    conn.close()
    return trial_number


def get_players_for_trial(trial_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM players WHERE trial_id = ? ORDER BY trial_number", (trial_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Attendance / Roll Call
# --------------------------------------------------------------------------- #

def set_attendance(player_id, trial_id, is_present):
    """Very basic upsert - delete any existing record then insert the new one.
    Works fine for the trial sizes this app deals with."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM attendance WHERE player_id = ? AND trial_id = ?", (player_id, trial_id)
    )
    conn.execute(
        "INSERT INTO attendance (player_id, trial_id, is_present) VALUES (?, ?, ?)",
        (player_id, trial_id, 1 if is_present else 0),
    )
    conn.commit()
    conn.close()


def get_attendance_map(trial_id):
    """Returns {player_id: 0/1} for every player who has a roll call record."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT player_id, is_present FROM attendance WHERE trial_id = ?", (trial_id,)
    ).fetchall()
    conn.close()
    return {r["player_id"]: r["is_present"] for r in rows}


def get_present_players(trial_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.* FROM players p
           JOIN attendance a ON a.player_id = p.player_id
           WHERE a.trial_id = ? AND a.is_present = 1
           ORDER BY p.trial_number""",
        (trial_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Rounds & Assignments
# --------------------------------------------------------------------------- #

def clear_rounds_for_trial(trial_id):
    """Wipes any previously generated rounds so a fresh draw can be saved.
    Assignments get cleaned up too since they reference round_id."""
    conn = get_connection()
    round_ids = [r["round_id"] for r in conn.execute(
        "SELECT round_id FROM rounds WHERE trial_id = ?", (trial_id,)
    ).fetchall()]
    for rid in round_ids:
        conn.execute("DELETE FROM assignments WHERE round_id = ?", (rid,))
    conn.execute("DELETE FROM rounds WHERE trial_id = ?", (trial_id,))
    conn.commit()
    conn.close()


def create_round_entry(trial_id, round_number, court_number, team, bib_colour):
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO rounds (trial_id, round_number, court_number, team, bib_colour)
           VALUES (?, ?, ?, ?, ?)""",
        (trial_id, round_number, court_number, team, bib_colour),
    )
    conn.commit()
    round_id = cur.lastrowid
    conn.close()
    return round_id


def create_assignment(round_id, player_id, position):
    conn = get_connection()
    conn.execute(
        "INSERT INTO assignments (round_id, player_id, position) VALUES (?, ?, ?)",
        (round_id, player_id, position),
    )
    conn.commit()
    conn.close()


def get_rounds_for_trial(trial_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM rounds WHERE trial_id = ? ORDER BY round_number, court_number, team",
        (trial_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_assignments_for_round(round_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.*, p.first_name, p.last_name, p.trial_number
           FROM assignments a
           JOIN players p ON p.player_id = a.player_id
           WHERE a.round_id = ?""",
        (round_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
