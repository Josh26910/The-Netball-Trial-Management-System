"""
players.py v1.1

Everything to do with player/trial data in one file: database schema and
CRUD (previously database.py), CSV export (previously export.py), CSV
import/bulk-seeding (previously seed_database.py), and the synthetic test
data generator (previously test_data.py). Merged together to cut down the
project to three files total - main.py (GUI + auth + styling), algorithm.py
(rotation engine), and this one (everything about player data).

Running this file directly (`python players.py`) does the same thing
seed_database.py used to: scans this script's own folder for *.csv files
and loads each one into its own trial. See seed_from_csv()'s docstring
section below for the two CSV formats it understands.

Added since last commit (merged in from a more advanced reference copy of
this project, after verifying each claim rather than trusting it blindly):
    - users table now stores a per-account salt for password hashing (see
      main.py's hash_password()) instead of a plain unsalted SHA-256
    - trials can optionally set min_birth_year/max_birth_year for FR3 age
      eligibility checking - see check_dob_eligibility()
    - backup_database() copies the live .db file into backups/ with a
      timestamp - contingency plan for corruption, called from main.py
      on startup and on demand
    - schema migration generalised from a players-table-only helper to
      cover trials/players/users together (_migrate_schema())
"""

import argparse
import csv
import glob
import hashlib
import os
import random
import shutil
import sqlite3
from datetime import datetime

DB_PATH = "netball_trials.db"
BACKUP_DIR = "backups"


def _hash_password(password, salt_hex):
    """Tiny local salted password hash, used only for seeding the default
    coordinator account on first run. Deliberately not importing main.py's
    auth logic here - main.py already imports this module for the database
    layer, so importing back would create a circular import.

    SHA-256 over salt + password, not just SHA-256(password): two accounts
    with the same password would otherwise get the same hash, and an
    attacker with the database file could compare against a precomputed
    table of common password hashes. The salt isn't secret - it's stored
    right alongside the hash - it just makes every hash unique.
    """
    salted = bytes.fromhex(salt_hex) + password.encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def _new_salt():
    return os.urandom(16).hex()


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
            trial_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            trial_name     TEXT NOT NULL,
            age_group      TEXT NOT NULL,
            trial_date     TEXT NOT NULL,
            num_courts     INTEGER NOT NULL DEFAULT 1 CHECK (num_courts IN (1, 2)),
            min_birth_year INTEGER,
            max_birth_year INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            trial_id        INTEGER NOT NULL,
            trial_number    INTEGER NOT NULL,
            first_name      TEXT NOT NULL,
            last_name       TEXT NOT NULL,
            dob             TEXT NOT NULL,
            netball_id      TEXT,
            address         TEXT,
            phone           TEXT,
            email           TEXT,
            parent_name     TEXT,
            parent_phone    TEXT,
            parent_email    TEXT,
            playing_history TEXT,
            position_1      TEXT NOT NULL,
            position_2      TEXT NOT NULL,
            position_3      TEXT,
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

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt          TEXT NOT NULL DEFAULT '',
            role          TEXT NOT NULL CHECK (
                            role IN ('coordinator', 'coach', 'referee', 'player')
                          )
        )
    """)

    conn.commit()

    _migrate_schema(c)
    conn.commit()

    # Seed a default coordinator account on first run so the app is usable
    # before any signup screen exists. Uses the local _hash_password()/
    # _new_salt() below rather than importing main.py's auth logic - that
    # would create a circular import (main.py imports players.py for the
    # database layer).
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'coordinator'")
    if c.fetchone()[0] == 0:
        salt = _new_salt()
        c.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            ("coordinator", _hash_password("coordinator123", salt), salt, "coordinator"),
        )
        conn.commit()

    conn.close()


def backup_database():
    """
    Copies the live database file into backups/ with a timestamped name.
    This is the contingency plan for database corruption described in the
    SAT's risk register - a coordinator losing an afternoon's worth of
    registrations to a corrupted file is a much bigger deal than the
    handful of KB a backup costs.

    Called once automatically at startup (see main.py), and also available
    for the coordinator to trigger on demand from the Export tab. Returns
    the backup file path, or None if there's no database yet to back up.
    """
    if not os.path.exists(DB_PATH):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"netball_trials_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


# Optional columns each table can be missing on an older database, keyed by
# table name, as (column_name, sql_type) pairs. Kept as one dict so
# _migrate_schema() and any future schema addition just means adding a
# tuple here instead of writing a new ALTER TABLE by hand.
OPTIONAL_COLUMNS = {
    "players": [
        (col, "TEXT") for col in (
            "netball_id", "address", "phone", "email", "parent_name",
            "parent_phone", "parent_email", "playing_history", "position_3",
        )
    ],
    "trials": [("min_birth_year", "INTEGER"), ("max_birth_year", "INTEGER")],
    "users": [("salt", "TEXT DEFAULT ''")],
}


def _migrate_schema(cursor):
    """
    CREATE TABLE IF NOT EXISTS only helps on a brand new database - it does
    nothing to a table that already exists from an older version of this
    app, which is exactly what caused 'table players has no column named
    netball_id' the first time the players table grew new fields. This
    checks which columns actually exist on each table right now (PRAGMA
    table_info) and ALTERs in whichever ones from OPTIONAL_COLUMNS are
    missing, so an existing netball_trials.db gets upgraded in place
    instead of everyone having to delete it and re-import everything after
    every schema change.

    Column types matter here, not just "make it work" - min_birth_year/
    max_birth_year need INTEGER affinity so numeric comparisons in
    check_dob_eligibility() behave correctly; a TEXT column storing
    numbers as text can sort/compare unexpectedly against real integers.
    """
    for table, columns in OPTIONAL_COLUMNS.items():
        existing = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table})")}
        for column, sql_type in columns:
            if column not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


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


def birth_year_of(dob_str):
    return datetime.strptime(dob_str.strip(), "%d/%m/%Y").year


def check_dob_eligibility(dob_str, min_birth_year, max_birth_year):
    """
    FR3: validates a player's DOB against the age eligibility window the
    coordinator set for the trial (e.g. born 2013-2014 for a U13 trial in
    2026). Returns (is_valid, message) - this is informational only, the
    coordinator may still register a player outside the window if an age
    permit applies, so this never blocks registration on its own.

    If the trial doesn't have a birth year window set (min/max are None),
    there's nothing to check against, so this reports valid with a note
    rather than a false warning.
    """
    if not is_valid_date(dob_str):
        return False, "Invalid date format (use DD/MM/YYYY)"
    if min_birth_year is None or max_birth_year is None:
        return True, "No age window set for this trial"
    year = birth_year_of(dob_str)
    if min_birth_year <= year <= max_birth_year:
        return True, f"\u2713 Valid ({year} is within {min_birth_year}\u2013{max_birth_year})"
    return False, f"\u26a0 Outside range ({year} not in {min_birth_year}\u2013{max_birth_year}) - permit required"


# --------------------------------------------------------------------------- #
# Trials
# --------------------------------------------------------------------------- #

def create_trial(trial_name, age_group, trial_date, num_courts=1,
                  min_birth_year=None, max_birth_year=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO trials (trial_name, age_group, trial_date, num_courts,
                                min_birth_year, max_birth_year)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (trial_name, age_group, trial_date, num_courts, min_birth_year, max_birth_year),
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


def create_player(trial_id, first_name, last_name, dob, position_1, position_2,
                   netball_id="", address="", phone="", email="", parent_name="",
                   parent_phone="", parent_email="", playing_history="", position_3=""):
    """
    Only trial_id, first_name, last_name, dob, position_1, position_2 are
    required - everything else defaults to an empty string so existing
    callers (test_data.py, the Players tab, etc.) that only pass the first
    six arguments keep working unchanged. The extra fields exist to support
    importing full registration data (see seed_database.py's raw CSV
    format) matching FR2's full 14-field spec.
    """
    trial_number = get_next_trial_number(trial_id)
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (trial_id, trial_number, first_name, last_name, dob,
                                 netball_id, address, phone, email, parent_name,
                                 parent_phone, parent_email, playing_history,
                                 position_1, position_2, position_3)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (trial_id, trial_number, first_name, last_name, dob, netball_id, address,
         phone, email, parent_name, parent_phone, parent_email, playing_history,
         position_1, position_2, position_3),
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


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #

def create_user(username, password_hash, role, salt=""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
        (username, password_hash, salt, role),
    )
    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


# --------------------------------------------------------------------------- #
# CSV EXPORT (previously export.py)
# --------------------------------------------------------------------------- #
# Clean CSV export of the player register for a trial (FR11). This was the
# #1 complaint about the old spreadsheet system - merged cells and dash
# placeholders for empty fields made the export unusable without 30+
# minutes of manual reformatting. This just writes a plain, well-formed
# CSV: one header row, one row per player, no merged cells, no dashes.

CSV_HEADERS = ["Trial No", "First Name", "Last Name", "DOB", "Position 1", "Position 2"]

PLAYER_FIELD_ORDER = ["trial_number", "first_name", "last_name", "dob", "position_1", "position_2"]


def export_players_csv(players, filepath):
    """
    Writes a clean CSV of player registrations.
    `players` is a list of dicts (as returned by get_players_for_trial()).
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
# CSV IMPORT / BULK SEEDING (previously seed_database.py)
# --------------------------------------------------------------------------- #
# Loads player data from CSV files back into the database. Auto-detects two
# formats: the CLEAN format this module's own export_players_csv() writes
# (has a header row), and a RAW format matching real registration exports
# (no header, blank trial number, one combined full-name field, and the
# full 14-field registration spec) in this fixed column order:
#     (blank), Full Name, DOB, Netball ID, Address, Phone, Email,
#     Parent Name, Parent Phone, Parent Email, Playing History,
#     Position 1, Position 2, Position 3 (optional)
RAW_COLUMNS = [
    "trial_no", "full_name", "dob", "netball_id", "address", "phone", "email",
    "parent_name", "parent_phone", "parent_email", "playing_history",
    "position_1", "position_2", "position_3",
]

def find_csv_files():
    """Returns every *.csv file sitting in the same folder as this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return sorted(glob.glob(os.path.join(script_dir, "*.csv")))


def _read_rows(filepath):
    """Reads every row of a CSV as plain lists (not dicts), using the csv
    module so quoted fields with embedded commas (like a street address)
    are handled correctly rather than splitting on every comma blindly."""
    with open(filepath, newline="", encoding="utf-8") as f:
        return [row for row in csv.reader(f) if row and any(cell.strip() for cell in row)]


def detect_format(rows):
    """Returns 'clean' if the first row looks like export.py's header,
    otherwise 'raw'."""
    if not rows:
        return "raw"
    first_row = [cell.strip() for cell in rows[0]]
    if first_row[:len(CSV_HEADERS)] == CSV_HEADERS:
        return "clean"
    return "raw"


def split_full_name(full_name):
    """Splits on the first space only, so multi-word surnames stay together
    as the last name (e.g. 'Mary Anne Smith' -> 'Mary' / 'Anne Smith')."""
    full_name = full_name.strip()
    if " " not in full_name:
        return full_name, ""  # single-word name, no surname given
    first, last = full_name.split(" ", 1)
    return first, last


def parse_clean_rows(rows):
    """Parses export.py's own CSV format (has a header row)."""
    players = []
    for row in rows[1:]:  # skip header
        if len(row) < 6:
            continue
        players.append({
            "first_name": row[1].strip(),
            "last_name": row[2].strip(),
            "dob": row[3].strip(),
            "position_1": row[4].strip(),
            "position_2": row[5].strip(),
        })
    return players


def parse_raw_rows(rows):
    """
    Parses the raw registration format (see module docstring) - no header,
    fixed column order, one combined full name field. If the first row's
    DOB-shaped column (index 2) doesn't actually parse as a date, it's
    treated as a header row and skipped instead of being read as a player.
    """
    start_index = 0
    if rows and len(rows[0]) > 2 and not is_valid_date(rows[0][2].strip()):
        start_index = 1  # first row was a header, not data

    players = []
    for row in rows[start_index:]:
        if len(row) < 13:
            continue  # not enough columns to be a real registration row

        full_name = row[1].strip()
        first_name, last_name = split_full_name(full_name)

        players.append({
            "first_name": first_name,
            "last_name": last_name,
            "dob": row[2].strip(),
            "netball_id": row[3].strip(),
            "address": row[4].strip(),
            "phone": row[5].strip(),
            "email": row[6].strip(),
            "parent_name": row[7].strip(),
            "parent_phone": row[8].strip(),
            "parent_email": row[9].strip(),
            "playing_history": row[10].strip(),
            "position_1": row[11].strip(),
            "position_2": row[12].strip(),
            "position_3": row[13].strip() if len(row) > 13 else "",
        })
    return players


def load_csv(filepath):
    """Reads a CSV file and returns a list of player dicts, auto-detecting
    whether it's in the clean export.py format or the raw registration
    format."""
    rows = _read_rows(filepath)
    fmt = detect_format(rows)
    if fmt == "clean":
        return parse_clean_rows(rows), fmt
    return parse_raw_rows(rows), fmt


def trial_name_from_filename(filepath):
    """'U13.csv' -> 'U13'. Also used as the age group."""
    return os.path.splitext(os.path.basename(filepath))[0]


def get_or_create_trial(trial_name, age_group, trial_date, num_courts):
    existing = next((t for t in get_all_trials() if t["trial_name"] == trial_name), None)
    if existing:
        return existing["trial_id"], False

    create_trial(trial_name, age_group, trial_date, num_courts)
    new_trial = next(t for t in get_all_trials() if t["trial_name"] == trial_name)
    return new_trial["trial_id"], True


def seed_from_csv(filepath, trial_date, num_courts):
    trial_name = trial_name_from_filename(filepath)
    age_group = trial_name

    try:
        players, fmt = load_csv(filepath)
    except (OSError, csv.Error) as e:
        print(f"{os.path.basename(filepath)}: skipped - could not read file ({e})")
        return 0, 0

    trial_id, created = get_or_create_trial(trial_name, age_group, trial_date, num_courts)
    status = "created" if created else "existing"

    loaded = 0
    skipped = 0
    for p in players:
        if not p["first_name"] or not p["last_name"]:
            skipped += 1
            continue
        if not is_valid_date(p["dob"]):
            skipped += 1
            continue

        create_player(
            trial_id, p["first_name"], p["last_name"], p["dob"],
            p["position_1"], p["position_2"],
            netball_id=p.get("netball_id", ""),
            address=p.get("address", ""),
            phone=p.get("phone", ""),
            email=p.get("email", ""),
            parent_name=p.get("parent_name", ""),
            parent_phone=p.get("parent_phone", ""),
            parent_email=p.get("parent_email", ""),
            playing_history=p.get("playing_history", ""),
            position_3=p.get("position_3", ""),
        )
        loaded += 1

    print(f"{os.path.basename(filepath)} [{fmt} format]: {status} trial '{trial_name}' "
          f"(id {trial_id}) - loaded {loaded}/{len(players)} players ({skipped} skipped)")
    return loaded, skipped


def prompt_for_shared_settings(args):
    if not args.date:
        args.date = input("Trial date for all trials (DD/MM/YYYY): ").strip()
    if not args.courts:
        courts_input = input("Number of courts for all trials (1 or 2) [1]: ").strip()
        args.courts = int(courts_input) if courts_input else 1
    return args


def main():
    parser = argparse.ArgumentParser(
        description="Scans this script's folder for CSV files and loads each one into its "
                     "own trial (named after the file). Handles both export.py's clean CSV "
                     "format and raw registration CSVs with the full field set."
    )
    parser.add_argument("--date", default=None, help="Trial date applied to every CSV, DD/MM/YYYY")
    parser.add_argument("--courts", type=int, choices=[1, 2], default=None,
                         help="Number of courts applied to every CSV (1 or 2, defaults to 1)")
    args = parser.parse_args()

    csv_files = find_csv_files()
    if not csv_files:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"No CSV files found in {script_dir} - nothing to load.")
        return

    print(f"Found {len(csv_files)} CSV file(s): {', '.join(os.path.basename(f) for f in csv_files)}")
    args = prompt_for_shared_settings(args)

    init_db()

    total_loaded = 0
    total_skipped = 0
    for filepath in csv_files:
        loaded, skipped = seed_from_csv(filepath, args.date, args.courts)
        total_loaded += loaded
        total_skipped += skipped

    print(f"\nDone - {total_loaded} player(s) loaded across {len(csv_files)} file(s), "
          f"{total_skipped} row(s) skipped.")



# --------------------------------------------------------------------------- #
# TEST DATA GENERATION (previously test_data.py)
# --------------------------------------------------------------------------- #
# Generates a roster of realistic-looking (but fake) test players, useful
# for exercising the Rounds tab / stress-testing without hand-typing 100
# players through the Players tab every time. Not used by the CLI import
# flow above - this is an importable utility for ad-hoc testing.
POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]

FIRST_NAMES = [
    "Emma", "Sophie", "Sarah", "Lena", "Aisha", "Mia", "Chloe", "Priya", "Lucy", "Amy",
    "Grace", "Zoe", "Ella", "Jade", "Olivia", "Isla", "Ruby", "Charlotte", "Ava", "Mia",
    "Willow", "Freya", "Harper", "Lily", "Matilda", "Zara", "Layla", "Maya", "Ivy", "Chelsea",
    "Georgia", "Holly", "Amelia", "Sienna", "Poppy", "Eve", "Bella", "Hannah", "Alicia", "Nina",
]

LAST_NAMES = [
    "Nguyen", "Tran", "Mohammed", "Park", "Ahmed", "Kovac", "Pham", "Sharma", "Tan", "Chen",
    "Wilson", "Brown", "Kowalski", "Robinson", "Smith", "Taylor", "Walker", "White", "Green",
    "Baker", "Hill", "King", "Scott", "Adams", "Nelson", "Carter", "Mitchell", "Roberts", "Turner",
    "Phillips", "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart", "Morris", "Rogers",
    "Reed", "Cook",
]


def _random_dob():
    """Random DOB within the U13 eligibility window used for the test trial (born 2013 or 2014)."""
    year = random.choice([2013, 2014])
    day = random.randint(1, 28)  # keeps it simple, avoids month-length edge cases
    month = random.randint(1, 12)
    return f"{day:02d}/{month:02d}/{year}"


def _random_positions():
    pos1 = random.choice(POSITIONS)
    pos2 = random.choice([p for p in POSITIONS if p != pos1])
    return pos1, pos2


def generate_test_players(count=100):
    random.seed(42)  # same 100 players every run, so test results are repeatable
    players = []
    for _ in range(count):
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        dob = _random_dob()
        pos1, pos2 = _random_positions()
        players.append((first_name, last_name, dob, pos1, pos2))
    return players


def load_test_players(count=100):
    trial_name = f"Test Trial ({count})"
    trials = get_all_trials()
    existing = next((t for t in trials if t["trial_name"] == trial_name), None)

    if existing:
        trial_id = existing["trial_id"]
        print(f"Using existing trial: {trial_name} (id {trial_id})")
    else:
        create_trial(trial_name, "U13", "01/09/2026")
        trial_id = next(t["trial_id"] for t in get_all_trials() if t["trial_name"] == trial_name)
        print(f"Created new trial '{trial_name}' (id {trial_id})")

    players = generate_test_players(count)
    for first_name, last_name, dob, pos1, pos2 in players:
        trial_number = create_player(trial_id, first_name, last_name, dob, pos1, pos2)
        print(f"  #{trial_number} {first_name} {last_name} ({pos1}/{pos2})")

    print(f"\nDone - {len(players)} test players added to trial id {trial_id}.")



if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------- #
# players.py v1.1
# --------------------------------------------------------------------------- #
