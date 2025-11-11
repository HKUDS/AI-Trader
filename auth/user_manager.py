"""
User Management Utilities
Provides functions for managing users and authentication
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict
from passlib.context import CryptContext

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Users database file path
USERS_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "users.json"
)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def load_users() -> Dict:
    """
    Load users from the JSON database file

    Returns:
        Dictionary of users {username: {password: hash, ...}}
    """
    if not os.path.exists(USERS_DB_PATH):
        # Create empty users database if it doesn't exist
        os.makedirs(os.path.dirname(USERS_DB_PATH), exist_ok=True)
        with open(USERS_DB_PATH, 'w') as f:
            json.dump({}, f)
        return {}

    try:
        with open(USERS_DB_PATH, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_users(users: Dict) -> None:
    """
    Save users to the JSON database file

    Args:
        users: Dictionary of users to save
    """
    os.makedirs(os.path.dirname(USERS_DB_PATH), exist_ok=True)
    with open(USERS_DB_PATH, 'w') as f:
        json.dump(users, f, indent=2)


def create_user(username: str, password: str, email: Optional[str] = None) -> bool:
    """
    Create a new user

    Args:
        username: Username for the new user
        password: Plain text password (will be hashed)
        email: Optional email address

    Returns:
        True if user was created, False if username already exists
    """
    users = load_users()

    if username in users:
        return False

    users[username] = {
        "password": get_password_hash(password),
        "email": email,
        "created_at": str(Path(USERS_DB_PATH).stat().st_mtime) if os.path.exists(USERS_DB_PATH) else None
    }

    save_users(users)
    return True


def authenticate_user(username: str, password: str) -> Optional[Dict]:
    """
    Authenticate a user with username and password

    Args:
        username: Username to authenticate
        password: Plain text password

    Returns:
        User data dictionary if authentication successful, None otherwise
    """
    users = load_users()

    if username not in users:
        return None

    user = users[username]

    if not verify_password(password, user["password"]):
        return None

    # Return user data without password
    user_data = user.copy()
    user_data.pop("password", None)
    user_data["username"] = username

    return user_data


def get_user(username: str) -> Optional[Dict]:
    """
    Get user data by username

    Args:
        username: Username to look up

    Returns:
        User data dictionary (without password) if found, None otherwise
    """
    users = load_users()

    if username not in users:
        return None

    user = users[username].copy()
    user.pop("password", None)
    user["username"] = username

    return user


def delete_user(username: str) -> bool:
    """
    Delete a user

    Args:
        username: Username to delete

    Returns:
        True if user was deleted, False if user not found
    """
    users = load_users()

    if username not in users:
        return False

    del users[username]
    save_users(users)
    return True


def initialize_default_users():
    """
    Initialize default users for development/testing
    Creates an admin user if no users exist
    """
    users = load_users()

    if not users:
        # Create default admin user
        create_user(
            username="admin",
            password="admin123",  # Change this in production!
            email="admin@ai-trader.com"
        )
        print("✅ Default admin user created (username: admin, password: admin123)")
