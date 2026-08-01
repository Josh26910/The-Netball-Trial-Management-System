"""
stress_test.py

Stress test for the round generation algorithm. Runs a batch of randomised
100-player rosters through generate_minimum_rounds() at 2 courts and checks
whether every player actually got both their preferred positions, and how
many rounds it took.

WHY THIS EXISTS
-----------------
This is what surfaced the starvation bug in the original greedy-scoring
algorithm. Out of 50 randomised 100-player rosters, 2 hit the 30-round
safety cap with a player still missing a preferred position. The cause:
scoring always favoured a "never had position_1 yet" candidate over a
"never had position_2 yet" candidate for a given slot, no matter how long
the position_2 candidate had already been waiting. If a position stayed in
high demand as someone's position_1 for long enough, a position_2-seeker
could get crowded out of it for a very long time - not permanently
impossible, but well past what should count as "fair".

This got fixed by reworking the selection logic in algorithm.py into a
reserved-slot design: genuinely needy players (still missing position_1 OR
position_2) are always served ahead of already-satisfied players, and
within a needy group, whoever has been waiting the longest gets priority
(via wait1/wait2 counters) instead of picking on preference strength alone.
A separate bench_wait counter keeps filler picks rotating fairly too.

Re-running this script after that fix: 0/50 rosters failed, all converging
in 11 rounds or fewer.

Keeping this script around so any future change to the algorithm gets
checked against the same 50 rosters before being trusted.
"""

import random

import algorithm

POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]
NUM_ROSTERS = 50
ROSTER_SIZE = 100
NUM_COURTS = 2


def random_roster(seed, n=ROSTER_SIZE):
    """Builds a roster of n players with randomised position_1/position_2
    preferences (never the same position twice for one player). Same seed
    always produces the same roster, so any failure can be reproduced
    exactly rather than being a one-off fluke."""
    random.seed(seed)
    players = []
    for i in range(n):
        pos1 = random.choice(POSITIONS)
        pos2 = random.choice([p for p in POSITIONS if p != pos1])
        players.append({"player_id": i + 1, "position_1": pos1, "position_2": pos2})
    return players


def run_stress_test():
    failures = 0
    max_rounds_seen = 0
    total_rounds = 0

    for seed in range(NUM_ROSTERS):
        players = random_roster(seed)
        rounds_output, rounds_used, failed = algorithm.generate_minimum_rounds(players, NUM_COURTS)

        max_rounds_seen = max(max_rounds_seen, rounds_used)
        total_rounds += rounds_used

        if failed:
            failures += 1
            print(f"Roster {seed:>2}: FAILED - {len(failed)} player(s) still missing a "
                  f"preference after {rounds_used} rounds")
        else:
            print(f"Roster {seed:>2}: OK - converged in {rounds_used} round(s)")

    print()
    print(f"{NUM_ROSTERS - failures}/{NUM_ROSTERS} rosters fully satisfied the guarantee (FR6)")
    print(f"Max rounds needed across all rosters: {max_rounds_seen}")
    print(f"Average rounds needed: {total_rounds / NUM_ROSTERS:.1f}")


if __name__ == "__main__":
    run_stress_test()


# --------------------------------------------------------------------------- #
# stress_test.py v1.0
# --------------------------------------------------------------------------- #
