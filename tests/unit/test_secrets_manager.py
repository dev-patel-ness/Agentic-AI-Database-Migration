"""Unit tests for Secrets Manager integration"""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from observability.secrets_manager import SecretsManagerClient, get_secrets_manager


@pytest.fixture
def secrets_manager():
    """Create a SecretsManagerClient for testing."""
    return SecretsManagerClient(region_name="us-east-1", use_env_fallback=True)


class TestSecretsManagerClient:
    """Tests for SecretsManager client functionality"""

    @pytest.mark.asyncio
    async def test_get_secret_from_manager(self, secrets_manager):
        """Test retrieving a secret from Secrets Manager."""
        expected_secret = {
            "username": "postgres",
            "password": "secret123",
            "host": "db.example.com",
            "port": 5432,
            "database": "migration_db"
        }

        with patch.object(secrets_manager.client, 'get_secret_value') as mock_get:
            mock_get.return_value = {
                "SecretString": json.dumps(expected_secret)
            }

            result = await secrets_manager.get_secret("capstone-staging/postgres-credentials")

            assert result == expected_secret
            mock_get.assert_called_once_with(SecretId="capstone-staging/postgres-credentials")

    @pytest.mark.asyncio
    async def test_get_secret_with_caching(self, secrets_manager):
        """Test secret caching to avoid repeated calls."""
        secret_value = {"key": "value"}

        with patch.object(secrets_manager.client, 'get_secret_value') as mock_get:
            mock_get.return_value = {"SecretString": json.dumps(secret_value)}

            # First call - should fetch from Secrets Manager
            result1 = await secrets_manager.get_secret("test-secret", use_cache=True)
            # Second call - should return from cache
            result2 = await secrets_manager.get_secret("test-secret", use_cache=True)

            assert result1 == secret_value
            assert result2 == secret_value
            assert mock_get.call_count == 1  # Only called once due to caching

    @pytest.mark.asyncio
    async def test_get_secret_fallback_to_env(self, secrets_manager):
        """Test fallback to environment variables when secret not found."""
        expected_secret = {"username": "admin", "password": "env_pass"}

        with patch.object(secrets_manager.client, 'get_secret_value') as mock_get:
            mock_get.side_effect = Exception("Secret not found")

            with patch.dict(os.environ, {"CAPSTONE_STAGING_DB_CREDENTIALS": json.dumps(expected_secret)}):
                result = await secrets_manager.get_secret("capstone-staging/db-credentials")

                assert result == expected_secret

    @pytest.mark.asyncio
    async def test_get_db_credentials(self, secrets_manager):
        """Test retrieving database credentials."""
        db_creds = {
            "username": "mysql_user",
            "password": "mysql_pass",
            "host": "mysql.example.com",
            "port": 3306,
            "database": "source_db"
        }

        with patch.object(secrets_manager, 'get_secret') as mock_get:
            mock_get.return_value = db_creds

            result = await secrets_manager.get_db_credentials("capstone-staging", "mysql")

            assert result == db_creds
            mock_get.assert_called_once_with("capstone-staging/mysql-credentials")

    @pytest.mark.asyncio
    async def test_get_bedrock_credentials(self, secrets_manager):
        """Test retrieving Bedrock credentials."""
        bedrock_creds = {
            "aws_access_key_id": "AKIA...",
            "aws_secret_access_key": "wJal...",
            "region": "us-east-1"
        }

        with patch.object(secrets_manager, 'get_secret') as mock_get:
            mock_get.return_value = bedrock_creds

            result = await secrets_manager.get_bedrock_credentials("capstone-staging")

            assert result == bedrock_creds
            mock_get.assert_called_once_with("capstone-staging/bedrock-config")

    @pytest.mark.asyncio
    async def test_get_langsmith_credentials(self, secrets_manager):
        """Test retrieving LangSmith credentials."""
        langsmith_creds = {
            "api_key": "ls_abc123xyz",
            "project_name": "capstone-staging"
        }

        with patch.object(secrets_manager, 'get_secret') as mock_get:
            mock_get.return_value = langsmith_creds

            result = await secrets_manager.get_langsmith_credentials("capstone-staging")

            assert result == langsmith_creds
            mock_get.assert_called_once_with("capstone-staging/langsmith-credentials")

    def test_invalidate_cache_specific_secret(self, secrets_manager):
        """Test invalidating cache for a specific secret."""
        secrets_manager._cache["secret1"] = {"key": "value1"}
        secrets_manager._cache["secret2"] = {"key": "value2"}

        secrets_manager.invalidate_cache("secret1")

        assert "secret1" not in secrets_manager._cache
        assert "secret2" in secrets_manager._cache

    def test_invalidate_cache_all(self, secrets_manager):
        """Test clearing all cache."""
        secrets_manager._cache["secret1"] = {"key": "value1"}
        secrets_manager._cache["secret2"] = {"key": "value2"}

        secrets_manager.invalidate_cache()

        assert len(secrets_manager._cache) == 0

    def test_env_fallback_with_json_parsing(self, secrets_manager):
        """Test environment variable fallback with JSON parsing."""
        creds = {"username": "admin", "password": "pass"}

        with patch.dict(os.environ, {"TEST_SECRET": json.dumps(creds)}):
            result = secrets_manager._get_secret_from_env("test/secret")

            assert result == creds

    def test_env_fallback_with_invalid_json(self, secrets_manager):
        """Test environment variable fallback with invalid JSON."""
        with patch.dict(os.environ, {"TEST_SECRET": "not-json"}):
            result = secrets_manager._get_secret_from_env("test/secret")

            assert result == {"raw_value": "not-json"}

    def test_env_fallback_missing_env_var(self, secrets_manager):
        """Test fallback returns None when env var not set."""
        result = secrets_manager._get_secret_from_env("nonexistent/secret")

        assert result is None

    def test_get_secrets_manager_singleton(self):
        """Test that get_secrets_manager returns a singleton."""
        sm1 = get_secrets_manager(region_name="us-east-1")
        sm2 = get_secrets_manager(region_name="eu-west-1")  # Different region, but same instance

        assert sm1 is sm2

    @pytest.mark.asyncio
    async def test_secrets_manager_no_fallback_raises(self, secrets_manager):
        """Test that exception is raised when fallback is disabled."""
        secrets_manager.use_env_fallback = False

        with patch.object(secrets_manager.client, 'get_secret_value') as mock_get:
            mock_get.side_effect = Exception("Secret not found")

            with pytest.raises(Exception):
                await secrets_manager.get_secret("test/secret")
