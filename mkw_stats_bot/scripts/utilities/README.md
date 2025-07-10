# Scripts Directory

This directory contains utility scripts for the MKW Stats Bot project.

## Utilities (`utilities/`)

One-off scripts for database management and development setup:

- `cleanup_database.py` - Clean up database by removing unused tables
- `delete_table.py` - Interactive script to delete specific database tables
- `init_simple_db.py` - Initialize a simple test database
- `setup_dev.py` - Development environment setup script
- `test_roster_commands.py` - Manual testing script for roster commands

## Usage

These scripts are not part of the main application and should be used carefully:

```bash
# Database cleanup
python scripts/utilities/cleanup_database.py

# Delete specific table
python scripts/utilities/delete_table.py --table tablename

# Initialize test database
python scripts/utilities/init_simple_db.py

# Set up development environment
python scripts/utilities/setup_dev.py
```

**Note**: These scripts directly modify the database. Use with caution and ensure you have backups.