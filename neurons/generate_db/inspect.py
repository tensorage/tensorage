import os
import sqlite3
import argparse

def investigate_db(db_path):
    # Check the size of the database
    db_size = os.path.getsize(db_path)
    print(f"Size of the database: {db_size / (1024 * 1024):.2f} MB")

    # Connect to the SQLite database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Fetch and print the schema of the database
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        print(f"\nSchema for table '{table_name}':")
        for column in columns:
            print(f"  {column[1]} ({column[2]})")

    # Close the connection
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Investigate the size and schema of an SQLite database.")
    parser.add_argument("--db_path", required=True, help="Path to the SQLite database.")
    args = parser.parse_args()

    investigate_db(args.db_path)