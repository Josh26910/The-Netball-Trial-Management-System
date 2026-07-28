"""
algorithm.py

FAIR POSITION ROTATION ALGORITHM - v1 (greedy scoring)
================================================================================

WHAT THIS NEEDS TO DO
----------------------
Every player registers with a 1st and 2nd preference position (GS, GA, WA, C,
WD, GD, GK). Across the trial rounds, the stakeholder requirement is that
EVERY present player gets at least one round in their position_1 and at least
one round in their position_2 (see FR6 in the SRS).

HOW IT WORKS
-------------
For every round, we go through each court, and for each court through the 7
positions for Team A then the 7 positions for Team B, always in the standard
netball order: GS, GA, WA, C, WD, GD, GK.

For each position slot, every player who hasn't already been placed THIS
ROUND (on ANY court - a player can only be in one place at a time) is scored
for how well they fit that slot:

    +10  it's their position_1 AND they have never played position_1 yet
    +6   it's their position_2 AND they have never played position_2 yet
    +2   it's their position_1 but they've already had a go at it
    +1   it's their position_2 but they've already had a go at it
    +0   not one of their preferences at all (last resort filler)

Whoever scores highest for that slot gets it, and a running counter is
updated so the algorithm knows who still "needs" their preferences in later
rounds.

ADDED SINCE LAST COMMIT
-------------------------
    - num_courts is now a parameter, so a trial with 2 courts fills 28 player
      slots per round (2 courts x 2 teams x 7 positions) instead of 14
    - generate_minimum_rounds(): instead of the coordinator guessing how many
      rounds to run, this keeps generating rounds (1, 2, 3, ...) until every
      present player has landed both preferred positions at least once, and
      just returns that. Capped at MAX_ROUNDS as a safety net in case a
      roster can never fully satisfy the guarantee (e.g. way more players
      than court capacity allows in a sane number of rounds).

KNOWN LIMITATION - TO REVISIT
-------------------------------
This is a purely greedy, round-by-round approach with no lookahead. There's
nothing stopping the same handful of high-scoring players from being picked
over and over for a popular position, which could leave a smaller group of
players stuck never landing their position_2 preference even after many
rounds. Need to stress test this properly with a large randomised roster
(50-100 players, 1-2 courts) before trusting it for real trial data - if
generate_minimum_rounds() hits MAX_ROUNDS and still reports failures, that's
the sign this scoring approach needs a rethink.
"""

POSITION_ORDER = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]
PLAYERS_PER_TEAM = 7
MAX_ROUNDS = 30  # safety cap for generate_minimum_rounds()

# Bib colours per court. Court 1 uses Black/White, Court 2 uses Red/Blue.
COURT_BIB_COLOURS = {
    1: {"A": "Black", "B": "White"},
    2: {"A": "Red", "B": "Blue"},
}


def _score_player(player, position, pos1_played, pos2_played):
    """Returns how good a fit `player` is for `position` in the current round.
    Higher is better. See the module docstring for the scoring rules."""
    player_id = player["player_id"]

    if position == player["position_1"] and pos1_played.get(player_id, 0) == 0:
        return 10
    if position == player["position_2"] and pos2_played.get(player_id, 0) == 0:
        return 6
    if position == player["position_1"]:
        return 2
    if position == player["position_2"]:
        return 1
    return 0


def _pick_best_player(candidates, position, pos1_played, pos2_played):
    """Picks the highest scoring candidate for this position. Ties just go to
    whichever player appears first in the list - not perfectly fair, but good
    enough for now."""
    best_player = None
    best_score = -1
    for player in candidates:
        score = _score_player(player, position, pos1_played, pos2_played)
        if score > best_score:
            best_score = score
            best_player = player
    return best_player


def generate_rounds(players, num_rounds, num_courts=1):
    """
    Generates `num_rounds` rounds of assignments across `num_courts` courts.

    players: list of player dicts (must have player_id, position_1, position_2)
    num_rounds: how many rounds to generate
    num_courts: 1 or 2

    Returns a list of round dicts:
        [
          {"round_number": 1, "court_number": 1, "team": "A", "assignments": [...]},
          {"round_number": 1, "court_number": 1, "team": "B", "assignments": [...]},
          {"round_number": 1, "court_number": 2, "team": "A", "assignments": [...]},
          ...
        ]

    Raises ValueError if there aren't enough present players to fill every
    court for a single round (14 per court).
    """
    players_needed = PLAYERS_PER_TEAM * 2 * num_courts
    if len(players) < players_needed:
        raise ValueError(
            f"Need at least {players_needed} present players for {num_courts} court(s), "
            f"got {len(players)}."
        )

    # Counters so the scoring function knows who has already had a go at
    # their 1st / 2nd preference position in a previous round.
    pos1_played = {p["player_id"]: 0 for p in players}
    pos2_played = {p["player_id"]: 0 for p in players}

    rounds_output = []

    for round_number in range(1, num_rounds + 1):
        used_this_round = []  # shared across ALL courts - a player is only ever in one place

        for court_number in range(1, num_courts + 1):
            for team in ("A", "B"):
                team_assignments = []

                for position in POSITION_ORDER:
                    candidates = [p for p in players if p["player_id"] not in used_this_round]

                    chosen = _pick_best_player(candidates, position, pos1_played, pos2_played)
                    if chosen is None:
                        # Shouldn't happen given the length check above, but guard
                        # against it anyway rather than crashing with an index error.
                        continue

                    team_assignments.append({"position": position, "player_id": chosen["player_id"]})
                    used_this_round.append(chosen["player_id"])

                    if position == chosen["position_1"]:
                        pos1_played[chosen["player_id"]] += 1
                    if position == chosen["position_2"]:
                        pos2_played[chosen["player_id"]] += 1

                rounds_output.append({
                    "round_number": round_number,
                    "court_number": court_number,
                    "team": team,
                    "assignments": team_assignments,
                })

    return rounds_output


def check_guarantee_met(players, rounds_output):
    """
    Returns a list of player_ids who did NOT get at least one round in
    position_1 AND at least one round in position_2 across all generated
    rounds. An empty list means the guarantee (FR6) was satisfied for
    everyone.
    """
    pos1_seen = set()
    pos2_seen = set()

    for round_data in rounds_output:
        for assignment in round_data["assignments"]:
            player = next((p for p in players if p["player_id"] == assignment["player_id"]), None)
            if player is None:
                continue
            if assignment["position"] == player["position_1"]:
                pos1_seen.add(player["player_id"])
            if assignment["position"] == player["position_2"]:
                pos2_seen.add(player["player_id"])

    failed = []
    for p in players:
        if p["player_id"] not in pos1_seen or p["player_id"] not in pos2_seen:
            failed.append(p["player_id"])
    return failed


def generate_minimum_rounds(players, num_courts=1, max_rounds=MAX_ROUNDS):
    """
    Instead of the coordinator having to guess how many rounds to generate,
    this starts at 1 round and keeps adding more until check_guarantee_met()
    comes back empty (everyone has had both their preferred positions), or
    until max_rounds is hit as a safety net.

    Returns (rounds_output, rounds_used, failed_player_ids). If failed_player_ids
    is not empty, max_rounds was reached without satisfying the guarantee for
    everyone - the caller should warn the coordinator about this.
    """
    rounds_output = []
    failed = []

    for num_rounds in range(1, max_rounds + 1):
        rounds_output = generate_rounds(players, num_rounds, num_courts)
        failed = check_guarantee_met(players, rounds_output)
        if not failed:
            return rounds_output, num_rounds, []

    return rounds_output, max_rounds, failed
