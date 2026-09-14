"""Create the FinAssist MySQL tables configured in DATABASE_URL.

Run: python -m Backend.init_db
"""

from .database import initialise_database


if __name__ == "__main__":
    initialise_database()
    print("FinAssist database schema is ready.")
