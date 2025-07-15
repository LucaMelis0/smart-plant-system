"""
LeaFi - MongoDB Database Initialization Module

This module sets up the MongoDB collections for the IoT plant monitoring system.
Implements data storage requirements for FR5 (Historical Data Logging).

Collections:
- users: Authentication and user management (NFR5: Data Security)
- sensor_data: Environmental readings storage (FR1: Plant Condition Monitoring)
- plant_status: Plant health evaluations (FR2: Status Evaluation)
- settings: User-configurable thresholds (FR7: System Calibration)
"""

from pymongo import MongoClient, ASCENDING
import bcrypt
import getpass
from datetime import datetime

def prompt_admin_credentials():
    """
    Interactive admin account setup.
    Prompts for username, password, and email.
    Implements secure credential collection for initial system setup.

    Returns:
        tuple: (username, password, email) for the admin account
    """
    print("\n=== LeaFi - Admin Setup ===")
    username = input("Admin username [admin]: ").strip() or "admin"

    while True:
        email = input("Admin email: ").strip()
        if not email:
            print("Email cannot be empty")
            continue
        # very basic email validation
        if "@" not in email or "." not in email:
            print("Please enter a valid email address")
            continue
        break

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

    return username, password, email

def init_database(mongo_uri="mongodb://localhost:27017/", db_name="LeaFi_storage"):
    """
    Initialize MongoDB with necessary collections and indexes.

    Creates all required collections for the LeaFi plant monitoring system:
    - Implements FR5: Historical Data Logging
    - Implements NFR5: Data Security (password hashing)
    - Implements FR7: System Calibration (settings storage)

    Args:
        mongo_uri (str): MongoDB connection URI
        db_name (str): Name of the MongoDB database
    """
    print("Initializing LeaFi MongoDB database...")

    client = MongoClient(mongo_uri)
    db = client[db_name]

    # Ensure indexes for unique username
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.sensor_data.create_index([("timestamp", ASCENDING)])
    db.plant_status.create_index([("timestamp", ASCENDING)])
    db.settings.create_index([("user_id", ASCENDING)], unique=True)

    # Create admin user if none exists
    if db.users.count_documents({}) == 0:
        username, password, email = prompt_admin_credentials()
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        admin_user = {
            "username": username,
            "password_hash": password_hash,
            "email": email,
            "created_at": datetime.now()
        }
        db.users.insert_one(admin_user)

        # Use the username as user_id for settings (for simplicity)
        default_settings = {
            "user_id": username,
            "min_humidity": 30.0,
            "max_temp": 35.0,
            "min_temp": 15.0,
            "min_light": 20,
            "max_light": 80,
            "location": "Cagliari"
        }
        db.settings.insert_one(default_settings)
        print(f"Admin user created: {username} ({email})")

    print("Database initialization completed successfully")

if __name__ == "__main__":
    print("LeaFi - MongoDB Database Setup Tool")
    init_database()