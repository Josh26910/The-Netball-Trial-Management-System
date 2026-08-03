"""
algorithm.py v2.0

FAIR POSITION ROTATION ALGORITHM - v2 (reserved-slot design)
================================================================================

WHAT THIS NEEDS TO DO
----------------------
Every player registers with a 1st and 2nd preference position (GS, GA, WA, C,
WD, GD, GK). Across the trial rounds, every present player must get at least
one round in their position_1 and at least one round in their position_2
(FR6 in the SRS).

WHY V1 GOT REPLACED
----------------------
The original algorithm scored every candidate for a slot and picked the
highest score (position_1-not-yet-played = 10, position_2-not-yet-played = 6,
already-played versions worth less, non-preference = 0). stress_test.py ran
50 randomised 100-player rosters through it at 2 courts, and 2 of them hit
the 30-round safety cap with a player still missing a preference.

The problem: position_1-need ALWAYS outscored position_2-need, with no
regard for how long the position_2-needing player had already been waiting.
If a position stayed in high demand as someone's position_1 for long enough
rounds in a row, a player who only needed it as their position_2 could keep
getting passed over round after round - not because the algorithm was
unfair on purpose, but because "urgency" was based purely on preference
rank, never on how long someone had actually been waiting.

HOW V2 WORKS
-------------
For every round, we go through each court, and for each court through the 7
positions for Team A then Team B, in standard netball order (GS...GK). For
each position slot, players who haven't already been placed THIS ROUND (on
any court) are split into tiers instead of scored individually:

    TIER 1 - "genuinely needy for position_1": this is their position_1 and
             they have never played it. Whoever in this tier has been
             waiting longest (see wait1 below) gets the slot.
    TIER 2 - "genuinely needy for position_2": only checked if tier 1 is
             empty. This is their position_2 and they have never played it.
             Longest-waiting in this tier gets the slot.
    TIER 3 - everyone else (already satisfied, or this isn't one of their
             preferences). Used as filler so the round can still be filled.
             Whoever has gone longest without playing ANY game (bench_wait)
             gets picked, so filler minutes rotate fairly too.

Three separate aging counters drive the "longest waiting" tie-breaks:
    wait1        - rounds spent still needing position_1
    wait2        - rounds spent still needing position_2
    bench_wait   - rounds spent not playing at all (any position)

All three reset to 0 for a player as soon as they're placed in a round
(wait1/wait2 only reset when the position placed actually satisfies that
specific preference; bench_wait resets whenever they play anything, since
that's about court time in general, not preference matching). Everyone
else who wasn't used this round gets their relevant counters incremented
by 1 at the end of the round.

This means a needy player can only be skipped by a HIGHER tier, never by
someone in the same tier who's waited less - which is what stops the v1
deadlock. Reserving tier 1 ahead of tier 2 is still a deliberate choice
(a still-unmet position_1 is treated as more urgent than a still-unmet
position_2), but within each tier nobody can be indefinitely passed over.

VALIDATION
-----------
Re-ran the same 50 randomised 100-player rosters from stress_test.py (the
two that failed under v1 included) through this version at 2 courts:
0/50 failures, worst case converged in 11 rounds, average 9.3 rounds. See
stress_test.py to re-run this check after any future change to the
selection logic.
"""

POSITION_ORDER = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]
PLAYERS_PER_TEAM = 7
MAX_ROUNDS = 30  # safety cap for generate_minimum_rounds()

# Bib colours per court. Court 1 uses Black/White, Court 2 uses Red/Blue.
COURT_BIB_COLOURS = {
    1: {"A": "Black", "B": "White"},
    2: {"A": "Red", "B": "Blue"},
}


def _pick_best_player(candidates, position, pos1_done, pos2_done, wait1, wait2, bench_wait):
    """
    Picks who fills this position slot, using the tiered reserved-slot logic
    described in the module docstring. Ties within a tier go to whoever has
    been waiting longest; a final tie-break on player_id just keeps the
    result deterministic (useful for testing/reproducing a specific roster).
    """
    tier1 = [p for p in candidates if position == p["position_1"] and not pos1_done[p["player_id"]]]
    if tier1:
        return max(tier1, key=lambda p: (wait1[p["player_id"]], -p["player_id"]))

    tier2 = [p for p in candidates if position == p["position_2"] and not pos2_done[p["player_id"]]]
    if tier2:
        return max(tier2, key=lambda p: (wait2[p["player_id"]], -p["player_id"]))

    if candidates:
        return max(candidates, key=lambda p: (bench_wait[p["player_id"]], -p["player_id"]))

    return None


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

    player_ids = [p["player_id"] for p in players]
    pos1_done = {pid: False for pid in player_ids}
    pos2_done = {pid: False for pid in player_ids}
    wait1 = {pid: 0 for pid in player_ids}
    wait2 = {pid: 0 for pid in player_ids}
    bench_wait = {pid: 0 for pid in player_ids}

    rounds_output = []

    for round_number in range(1, num_rounds + 1):
        used_this_round = []  # shared across ALL courts - a player is only ever in one place

        for court_number in range(1, num_courts + 1):
            for team in ("A", "B"):
                team_assignments = []

                for position in POSITION_ORDER:
                    candidates = [p for p in players if p["player_id"] not in used_this_round]

                    chosen = _pick_best_player(
                        candidates, position, pos1_done, pos2_done, wait1, wait2, bench_wait
                    )
                    if chosen is None:
                        # Shouldn't happen given the length check above, but guard
                        # against it anyway rather than crashing with an index error.
                        continue

                    pid = chosen["player_id"]
                    team_assignments.append({"position": position, "player_id": pid})
                    used_this_round.append(pid)

                    # Only satisfy + reset the counter for the preference this
                    # slot actually matches (a player could be placed here as
                    # filler and not have either preference matched at all).
                    if position == chosen["position_1"] and not pos1_done[pid]:
                        pos1_done[pid] = True
                        wait1[pid] = 0
                    if position == chosen["position_2"] and not pos2_done[pid]:
                        pos2_done[pid] = True
                        wait2[pid] = 0
                    bench_wait[pid] = 0

                rounds_output.append({
                    "round_number": round_number,
                    "court_number": court_number,
                    "team": team,
                    "assignments": team_assignments,
                })

        # End of round: age everyone who didn't play at all this round.
        for pid in player_ids:
            if pid in used_this_round:
                continue
            if not pos1_done[pid]:
                wait1[pid] += 1
            if not pos2_done[pid]:
                wait2[pid] += 1
            bench_wait[pid] += 1

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


# --------------------------------------------------------------------------- #
# algorithm.py v2.0
# --------------------------------------------------------------------------- #
