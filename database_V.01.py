"""
database.py
Very first version of the database layer for the Netball Trial app.

Just enough to create trials and register players. Attendance, rounds,
exports and login will get added later once the basic data model works.
"""

import sqlite3

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
            trial_date TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            trial_id     INTEGER NOT NULL,
            first_name   TEXT NOT NULL,
            last_name    TEXT NOT NULL,
            dob          TEXT NOT NULL,
            position_1   TEXT NOT NULL,
            position_2   TEXT NOT NULL,
            FOREIGN KEY (trial_id) REFERENCES trials(trial_id)
        )
    """)

    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# Trials
# --------------------------------------------------------------------------- #

def create_trial(trial_name, age_group, trial_date):
    conn = get_connection()
    conn.execute(
        "INSERT INTO trials (trial_name, age_group, trial_date) VALUES (?, ?, ?)",
        (trial_name, age_group, trial_date),
    )
    conn.commit()
    conn.close()


def get_all_trials():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM trials ORDER BY trial_date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Players
# --------------------------------------------------------------------------- #

def create_player(trial_id, first_name, last_name, dob, position_1, position_2):
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (trial_id, first_name, last_name, dob, position_1, position_2)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (trial_id, first_name, last_name, dob, position_1, position_2),
    )
    conn.commit()
    conn.close()


def get_players_for_trial(trial_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM players WHERE trial_id = ?", (trial_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
