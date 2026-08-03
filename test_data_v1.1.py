"""
test_data.py v1.1

Generates a roster of 100 test players and inserts them into a trial, so
the rotation algorithm can be tested at something closer to real trial
size (the SRS talks about 100+ players registering - a hardcoded list of
14 wasn't going to cut it for that).

Names are randomly paired from two name pools rather than typed out by
hand. DOBs are randomised within the U13 birth year window (2013-2014),
and position preferences are randomised too (position_2 is always
different from position_1). A fixed random seed is used so the same 100
players get generated every time this is run, which matters for repeatable
testing.

Usage:
    1. Run: python test_data.py
       (creates a "Test Trial (100)" if one doesn't already exist)
    2. Go to the Roll Call tab and mark everyone present, then generate
       rounds as normal.

NOTE: the algorithm only supports a single court (14 players per round)
right now, so with 100 present players it will take a lot more rounds
before everyone has had a game in both their preferred positions - that's
expected at this stage, not a bug. Multi-court support is still to come.
"""

import random

import database

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
    trials = database.get_all_trials()
    existing = next((t for t in trials if t["trial_name"] == trial_name), None)

    if existing:
        trial_id = existing["trial_id"]
        print(f"Using existing trial: {trial_name} (id {trial_id})")
    else:
        database.create_trial(trial_name, "U13", "01/09/2026")
        trial_id = next(t["trial_id"] for t in database.get_all_trials() if t["trial_name"] == trial_name)
        print(f"Created new trial '{trial_name}' (id {trial_id})")

    players = generate_test_players(count)
    for first_name, last_name, dob, pos1, pos2 in players:
        trial_number = database.create_player(trial_id, first_name, last_name, dob, pos1, pos2)
        print(f"  #{trial_number} {first_name} {last_name} ({pos1}/{pos2})")

    print(f"\nDone - {len(players)} test players added to trial id {trial_id}.")


if __name__ == "__main__":
    database.init_db()
    load_test_players(100)


# --------------------------------------------------------------------------- #
# test_data.py v1.1
# --------------------------------------------------------------------------- #
