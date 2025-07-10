# Admin Directory

This directory contains administrative scripts for managing the MKW Stats Bot.

## Scripts

- `setup_players.py` - Initialize database and add clan members to the roster
- `manage_nicknames.py` - Manage player nicknames and aliases
- `check_database.py` - Check database health and display statistics
- `reset_database.py` - Reset database to clean state (removes all data)

## Usage

These scripts are designed for regular administrative tasks:

```bash
# Initial setup - add clan members to roster
python admin/setup_players.py

# Manage player nicknames
python admin/manage_nicknames.py

# Check database status
python admin/check_database.py

# Reset database (WARNING: removes all data)
python admin/reset_database.py
```

Run these scripts from the project root directory.