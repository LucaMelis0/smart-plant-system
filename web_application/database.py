"""
LeaFi - MongoDB Database Initialization Module

This module sets up the MongoDB collections for the IoT plant monitoring system.
Handles admin user creation and secure SMTP config (with password encryption).
The SMTP encryption key is generated only if not present and must be manually
copied into your environment as LEAFI_SMTP_KEY for backend/server usage.
"""

from pymongo import MongoClient, ASCENDING
import bcrypt
import getpass
from datetime import datetime
import os
from cryptography.fernet import Fernet

def get_or_create_key():
    """
    Generates or retrieves the Fernet encryption key for SMTP password encryption.
    If not present in the environment, generates a new one and prints it so
    the user can save it as LEAFI_SMTP_KEY for future backend/server usage.
    """
    key = os.environ.get('LEAFI_SMTP_KEY')
    if not key:
        key = Fernet.generate_key()
        print("\n[IMPORTANT] A new SMTP encryption key was generated for you.\n"
              "==> COPY THIS KEY and set it as LEAFI_SMTP_KEY in your environment (.env or export):\n")
        print(f"LEAFI_SMTP_KEY={key.decode()}\n")
        print("Your SMTP password is now encrypted in the database with this key.")
        print("To run the backend, you MUST set this key as LEAFI_SMTP_KEY in your environment!")
    else:
        key = key.encode()
    return key

def prompt_admin_credentials():
    """
    Interactive admin account setup.
    Prompts for username, password, and notification email.
    Returns (username, password, email).
    """
    print("\n=== LeaFi - Admin Setup ===")
    username = input("Admin username [admin]: ").strip() or "admin"
    while True:
        email = input("Destination email for notifications (receiver): ").strip()
        if not email:
            print("Email cannot be empty")
            continue
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

def prompt_smtp_config(key):
    """
    Prompt user for SMTP configuration and encrypt the SMTP password.
    Returns a dict for MongoDB insertion.
    """
    print("\n=== LeaFi - SMTP Email Sending Configuration ===")
    smtp_server = input("SMTP server [smtp.gmail.com]: ").strip() or "smtp.gmail.com"
    smtp_port = input("SMTP port [465]: ").strip() or "465"
    smtp_username = input("SMTP username (your app Gmail address): ").strip()
    while True:
        smtp_password = getpass.getpass("SMTP password (App password for Gmail): ").strip()
        if not smtp_password:
            print("SMTP password cannot be empty")
            continue
        break
    sender_email = input("Sender email (usually same as SMTP username): ").strip() or smtp_username

    fernet = Fernet(key)
    encrypted_password = fernet.encrypt(smtp_password.encode()).decode()

    return {
        "type": "email",
        "smtp_server": smtp_server,
        "smtp_port": int(smtp_port),
        "smtp_username": smtp_username,
        "smtp_password": encrypted_password,  # Encrypted!
        "sender_email": sender_email
    }

def init_database(mongo_uri="mongodb://localhost:27017/", db_name="LeaFi_storage"):
    """
    Initialize MongoDB collections and admin user.
    If run at backend startup, also sets up SMTP config and encryption key.
    Prints the encryption key if not present to be saved by the user.
    """
    print("Initializing LeaFi MongoDB database...")
    client = MongoClient(mongo_uri)
    db = client[db_name]
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.sensor_data.create_index([("timestamp", ASCENDING)])
    db.plant_status.create_index([("timestamp", ASCENDING)])
    db.settings.create_index([("user_id", ASCENDING)], unique=True)
    db.config.create_index([("type", ASCENDING)], unique=True)

    # Admin user setup (if not present)
    if db.users.count_documents({}) == 0:
        username, password, dest_email = prompt_admin_credentials()
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        admin_user = {
            "username": username,
            "password_hash": password_hash,
            "email": dest_email,
            "created_at": datetime.now()
        }
        db.users.insert_one(admin_user)
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
        print(f"Admin user created: {username} (notifications sent to: {dest_email})")

    # SMTP config (always prompt at setup)
    key = get_or_create_key()
    smtp_config = prompt_smtp_config(key)
    db.config.update_one(
        {"type": "email"},
        {"$set": smtp_config},
        upsert=True
    )
    print("SMTP email configuration saved (with encrypted password).")
    print("Database initialization completed successfully.")
    print(
        "[INFO] If you generated a key above, remember to set LEAFI_SMTP_KEY in your environment "
        "before running the backend!"
    )

if __name__ == "__main__":
    print("LeaFi - MongoDB Database Setup Tool")
    init_database()