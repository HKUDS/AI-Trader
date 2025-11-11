"""
Integration tests for Authentication API endpoints
"""

import pytest
import os
import sys
from fastapi.testclient import TestClient

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from auth.auth_service import app
from auth import user_manager


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and teardown for each test"""
    # Setup: Use test database
    test_db_path = os.path.join(project_root, "data", "test_users_api.json")
    original_db_path = user_manager.USERS_DB_PATH
    user_manager.USERS_DB_PATH = test_db_path

    # Clear test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    yield

    # Teardown: Restore original database and cleanup
    user_manager.USERS_DB_PATH = original_db_path
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


class TestAuthEndpoints:
    """Test authentication endpoints"""

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "AI-Trader Authentication Service"
        assert data["status"] == "running"

    def test_register_user(self, client):
        """Test user registration"""
        response = client.post(
            "/auth/register",
            json={
                "username": "newuser",
                "password": "password123",
                "email": "newuser@example.com"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"

    def test_register_duplicate_user(self, client):
        """Test registering duplicate username"""
        # Register first user
        client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        # Try to register same username
        response = client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "password": "password456"
            }
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_register_invalid_username(self, client):
        """Test registration with invalid username"""
        response = client.post(
            "/auth/register",
            json={
                "username": "ab",  # Too short
                "password": "password123"
            }
        )

        assert response.status_code == 422

    def test_register_invalid_password(self, client):
        """Test registration with invalid password"""
        response = client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "password": "12345"  # Too short
            }
        )

        assert response.status_code == 422

    def test_login_success(self, client):
        """Test successful login"""
        # Register user
        client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        # Login
        response = client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        """Test login with wrong password"""
        # Register user
        client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        # Login with wrong password
        response = client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )

        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user"""
        response = client.post(
            "/auth/login",
            json={
                "username": "nonexistent",
                "password": "password123"
            }
        )

        assert response.status_code == 401

    def test_get_current_user(self, client):
        """Test getting current user info"""
        # Register and login
        client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "password": "password123",
                "email": "test@example.com"
            }
        )

        login_response = client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        token = login_response.json()["access_token"]

        # Get current user
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"

    def test_get_current_user_no_token(self, client):
        """Test getting current user without token"""
        response = client.get("/auth/me")

        assert response.status_code == 403

    def test_get_current_user_invalid_token(self, client):
        """Test getting current user with invalid token"""
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401

    def test_verify_token(self, client):
        """Test token verification endpoint"""
        # Register and login
        client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        login_response = client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        token = login_response.json()["access_token"]

        # Verify token
        response = client.post(
            "/auth/verify",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["username"] == "testuser"

    def test_refresh_token(self, client):
        """Test token refresh"""
        # Register and login
        client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        login_response = client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )

        refresh_token = login_response.json()["refresh_token"]

        # Refresh token
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_token_invalid(self, client):
        """Test refresh with invalid token"""
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid_token"}
        )

        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
