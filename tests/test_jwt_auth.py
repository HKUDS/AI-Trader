"""
Unit tests for JWT authentication
"""

import pytest
import os
import sys
import json
from datetime import datetime, timedelta

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from auth.jwt_utils import (
    create_access_token,
    create_refresh_token,
    verify_token,
    get_token_expiration
)
from auth.user_manager import (
    get_password_hash,
    verify_password,
    create_user,
    authenticate_user,
    get_user,
    load_users,
    save_users
)


class TestJWTUtils:
    """Test JWT utility functions"""

    def test_create_access_token(self):
        """Test creating an access token"""
        token = create_access_token(data={"sub": "testuser"})
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        """Test creating a refresh token"""
        token = create_refresh_token(data={"sub": "testuser"})
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_access_token(self):
        """Test verifying an access token"""
        token = create_access_token(data={"sub": "testuser"})
        payload = verify_token(token, token_type="access")

        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["type"] == "access"

    def test_verify_refresh_token(self):
        """Test verifying a refresh token"""
        token = create_refresh_token(data={"sub": "testuser"})
        payload = verify_token(token, token_type="refresh")

        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_verify_wrong_token_type(self):
        """Test that verifying wrong token type fails"""
        access_token = create_access_token(data={"sub": "testuser"})
        payload = verify_token(access_token, token_type="refresh")

        assert payload is None

    def test_verify_expired_token(self):
        """Test that expired token verification fails"""
        # Create token that expires immediately
        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(seconds=-1)
        )
        payload = verify_token(token, token_type="access")

        assert payload is None

    def test_get_token_expiration(self):
        """Test getting token expiration time"""
        token = create_access_token(data={"sub": "testuser"})
        expiration = get_token_expiration(token)

        assert expiration is not None
        assert isinstance(expiration, datetime)
        assert expiration > datetime.utcnow()


class TestUserManager:
    """Test user management functions"""

    def setup_method(self):
        """Setup test environment before each test"""
        # Use a temporary users file for testing
        self.test_users_file = os.path.join(
            project_root,
            "data",
            "test_users.json"
        )

        # Backup original USERS_DB_PATH
        from auth import user_manager
        self.original_db_path = user_manager.USERS_DB_PATH
        user_manager.USERS_DB_PATH = self.test_users_file

        # Clear test users
        if os.path.exists(self.test_users_file):
            os.remove(self.test_users_file)

    def teardown_method(self):
        """Cleanup after each test"""
        # Restore original USERS_DB_PATH
        from auth import user_manager
        user_manager.USERS_DB_PATH = self.original_db_path

        # Remove test users file
        if os.path.exists(self.test_users_file):
            os.remove(self.test_users_file)

    def test_password_hashing(self):
        """Test password hashing and verification"""
        password = "testpassword123"
        hashed = get_password_hash(password)

        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False

    def test_create_user(self):
        """Test creating a new user"""
        success = create_user("testuser", "testpass123", "test@example.com")

        assert success is True

        # Try creating same user again
        success = create_user("testuser", "testpass123")
        assert success is False

    def test_authenticate_user(self):
        """Test user authentication"""
        # Create user
        create_user("testuser", "testpass123", "test@example.com")

        # Authenticate with correct credentials
        user = authenticate_user("testuser", "testpass123")
        assert user is not None
        assert user["username"] == "testuser"
        assert user["email"] == "test@example.com"
        assert "password" not in user

        # Authenticate with wrong password
        user = authenticate_user("testuser", "wrongpassword")
        assert user is None

        # Authenticate non-existent user
        user = authenticate_user("nonexistent", "password")
        assert user is None

    def test_get_user(self):
        """Test getting user data"""
        # Create user
        create_user("testuser", "testpass123", "test@example.com")

        # Get user
        user = get_user("testuser")
        assert user is not None
        assert user["username"] == "testuser"
        assert "password" not in user

        # Get non-existent user
        user = get_user("nonexistent")
        assert user is None


@pytest.fixture
def test_users_data():
    """Fixture providing test user data"""
    return {
        "testuser1": {
            "password": get_password_hash("password1"),
            "email": "user1@example.com"
        },
        "testuser2": {
            "password": get_password_hash("password2"),
            "email": "user2@example.com"
        }
    }


def test_load_save_users(test_users_data):
    """Test loading and saving users"""
    from auth import user_manager

    # Save users
    test_file = os.path.join(project_root, "data", "test_save_users.json")
    original_db_path = user_manager.USERS_DB_PATH
    user_manager.USERS_DB_PATH = test_file

    try:
        save_users(test_users_data)

        # Load users
        loaded_users = load_users()
        assert loaded_users == test_users_data

    finally:
        # Cleanup
        user_manager.USERS_DB_PATH = original_db_path
        if os.path.exists(test_file):
            os.remove(test_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
