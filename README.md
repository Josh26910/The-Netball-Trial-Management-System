# Netball Trial Management System

VCE Software Development Units 3 & 4 - School-Assessed Task.
Python 3.12, Tkinter, SQLite. No extra packages needed.

## Files

- `main.py` - the app (GUI, login, roles)
- `algorithm.py` - the position rotation algorithm
- `players.py` - database, CSV export/import, test data

All three need to be in the same folder.

## Running it

```
python main.py
```

Default login on first run:

- Username: `coordinator`
- Password: `coordinator123`

## Loading test players

```
python -c "import players; players.init_db(); players.create_trial('U13 2026', 'U13', '11/09/2026', 2); tid = players.get_all_trials()[0]['trial_id']; [players.create_player(tid, *p) for p in players.generate_test_players(100)]"
```

Or put CSV files in the same folder and run:

```
python players.py
```

## Checking the algorithm

```
python algorithm.py
```
