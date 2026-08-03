# The-Netball-Trial-Management-System
The Netball Trial Management System
Add CSV export for player registrations

- New export.py module (v1.0) with export_players_csv(), writes a
  clean CSV with one header row and one row per player - no merged
  cells or dash placeholders like the old spreadsheet exports
- New Export tab in main.py (v1.4) with a save-file dialog, defaults
  the filename to <TrialName>_players.csv
- Tested against real trial data end to end, output opens cleanly

Addresses FR11. PDF trial sheet export (FR10) still to come.
