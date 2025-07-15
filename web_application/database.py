"""
LeaFi - Database Initialization Module

This module sets up the SQLite database structure for the IoT plant monitoring system.
Implements data storage requirements for FR5 (Historical Data Logging).

Database Schema:
- users: Authentication and user management (NFR5: Data Security)
- sensor_data: Environmental readings storage (FR1: Plant Condition Monitoring)
- plant_status: Plant health evaluations (FR2: Status Evaluation)
- settings: User-configurable thresholds (FR7: System Calibration)
"""

import sqlite3
import bcrypt
import getpass


def prompt_admin_credentials():
    """
    Interactive admin account setup
    Implements secure credential collection for initial system setup

    Returns:
        tuple: (username, password) for admin account
    """
    print("\n=== LeaFi - Admin Setup ===")
    username = input("Admin username [admin]: ").strip() or "admin"

    while True:
        password = getpass.getpass("Admin password: ").strip()
        password_confirm = getpass.getpass("Confirm password: ").strip()

        if not password:
            print("Password cannot be empty")
            continue
        if password != password_confirm:
            print("Passwords do not match - please try again")
            continue
        break

    return username, password


def init_database(db_path='LeaFi_storage.db'):
    """
    Initialize SQLite database with complete schema

    Creates all required tables for the LeaFi plant monitoring system:
    - Implements FR5: Historical Data Logging
    - Implements NFR5: Data Security (password hashing)
    - Implements FR7: System Calibration (settings storage)

    Args:
        db_path (str): Path to SQLite database file
    """
    print("Initializing LeaFi database...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # NFR5: User authentication table with secure password storage
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS users
                   (
                       id            INTEGER PRIMARY KEY AUTOINCREMENT,
                       username      TEXT UNIQUE NOT NULL,
                       password_hash TEXT        NOT NULL,
                       created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                   )
                   ''')

    # FR1 & FR5: Sensor data storage for environmental monitoring
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS sensor_data
                   (
                       id          INTEGER PRIMARY KEY AUTOINCREMENT,
                       temperature REAL    NOT NULL,
                       humidity    REAL    NOT NULL,
                       light_level INTEGER NOT NULL,
                       timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                   )
                   ''')

    # FR2 & FR5: Plant status evaluation results storage
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS plant_status
                   (
                       id              INTEGER PRIMARY KEY AUTOINCREMENT,
                       status          TEXT NOT NULL,
                       recommendations TEXT,
                       timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                   )
                   ''')

    # FR7: User-configurable plant care thresholds
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS settings
                   (
                       id           INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id      INTEGER,
                       min_humidity REAL DEFAULT 30,
                       max_temp     REAL DEFAULT 35,
                       min_temp     REAL DEFAULT 15,
                       min_light    REAL DEFAULT 20,
                       max_light    REAL DEFAULT 80,
                       location     TEXT DEFAULT 'Cagliari',
                       FOREIGN KEY (user_id) REFERENCES users (id)
                   )
                   ''')

    # Create admin user if no users exist
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        username, password = prompt_admin_credentials()

        # NFR5: Secure password hashing
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                       (username, password_hash))

        # Get admin user ID for settings
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        admin_id = cursor.fetchone()[0]

        # FR7: Create default plant care settings
        cursor.execute('''
                       INSERT INTO settings (user_id, min_humidity, max_temp, min_temp, min_light, max_light, location)
                       VALUES (?, 30, 35, 15, 20, 80, 'Cagliari')
                       ''', (admin_id,))

        print(f"Admin user created: {username}")

    conn.commit()
    conn.close()
    print("Database initialization completed successfully")


if __name__ == "__main__":
    print("LeaFi - Database Setup Tool")
    init_database()