"""
AWS Secrets Manager integration for runtime secret retrieval.

Provides async access to DB credentials, API keys, and other sensitive config
stored in AWS Secrets Manager. Falls back to environment variables for local dev.
"""

import json
import logging
import os
from typing import Optional, Any, Dict

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class SecretsManagerClient:
    """Async wrapper around AWS Secrets Manager for credential retrieval."""

    def __init__(self, region_name: str = "us-east-1", use_env_fallback: bool = True):
        """
        Initialize Secrets Manager client.

        Args:
            region_name: AWS region (default: us-east-1)
            use_env_fallback: Fall back to environment variables if secret not found (default: True)
        """
        self.region_name = region_name
        self.use_env_fallback = use_env_fallback
        self._client = None
        self._cache: Dict[str, Any] = {}

    @property
    def client(self):
        """Lazy-initialize boto3 Secrets Manager client."""
        if self._client is None:
            self._client = boto3.client("secretsmanager", region_name=self.region_name)
        return self._client

    async def get_secret(self, secret_name: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Retrieve a secret from Secrets Manager.

        Args:
            secret_name: Name of the secret (e.g., "capstone-staging/db-credentials")
            use_cache: Cache the result to avoid repeated calls (default: True)

        Returns:
            Dictionary with secret value, or None if not found and fallback disabled.

        Raises:
            ClientError: If Secrets Manager call fails (unless fallback is enabled).
        """
        # Check cache
        if use_cache and secret_name in self._cache:
            logger.debug(f"Returning cached secret: {secret_name}")
            return self._cache[secret_name]

        try:
            logger.debug(f"Fetching secret from Secrets Manager: {secret_name}")
            response = self.client.get_secret_value(SecretId=secret_name)

            # Parse JSON if needed
            if "SecretString" in response:
                secret_value = json.loads(response["SecretString"])
            else:
                secret_value = response["SecretBinary"]

            # Cache result
            if use_cache:
                self._cache[secret_name] = secret_value

            return secret_value

        except (ClientError, BotoCoreError) as e:
            logger.warning(f"Failed to retrieve secret {secret_name}: {e}")

            if self.use_env_fallback:
                logger.info(f"Falling back to environment variables for {secret_name}")
                return self._get_secret_from_env(secret_name)
            else:
                raise

    async def get_db_credentials(
        self, cluster_name: str, dialect: str
    ) -> Dict[str, Any]:
        """
        Retrieve database credentials for a specific cluster and dialect.

        Expected secret structure in Secrets Manager:
        {
            "username": "...",
            "password": "...",
            "host": "...",
            "port": ...,
            "database": "..."
        }

        Args:
            cluster_name: Cluster name (e.g., "capstone-staging")
            dialect: Database dialect (e.g., "postgresql", "mysql", "oracle")

        Returns:
            Dictionary with DB connection details.
        """
        secret_name = f"{cluster_name}/{dialect}-credentials"
        return await self.get_secret(secret_name) or {}

    async def get_bedrock_credentials(self, cluster_name: str) -> Dict[str, str]:
        """
        Retrieve AWS Bedrock credentials/config.

        Expected secret structure:
        {
            "aws_access_key_id": "...",
            "aws_secret_access_key": "...",
            "region": "..."
        }

        Args:
            cluster_name: Cluster name (e.g., "capstone-staging")

        Returns:
            Dictionary with Bedrock auth config.
        """
        secret_name = f"{cluster_name}/bedrock-config"
        return await self.get_secret(secret_name) or {}

    async def get_langsmith_credentials(self, cluster_name: str) -> Dict[str, str]:
        """
        Retrieve LangSmith API credentials.

        Expected secret structure:
        {
            "api_key": "...",
            "project_name": "..."
        }

        Args:
            cluster_name: Cluster name

        Returns:
            Dictionary with LangSmith config.
        """
        secret_name = f"{cluster_name}/langsmith-credentials"
        return await self.get_secret(secret_name) or {}

    def _get_secret_from_env(self, secret_name: str) -> Optional[Dict[str, Any]]:
        """
        Fallback to environment variables for local dev.

        Converts secret name to uppercase with underscores, e.g.:
        - "capstone-staging/db-credentials" → "CAPSTONE_STAGING_DB_CREDENTIALS"
        - "capstone-staging/bedrock-config" → "CAPSTONE_STAGING_BEDROCK_CONFIG"

        Args:
            secret_name: Secret name in Secrets Manager

        Returns:
            Parsed JSON from environment variable, or None if not set.
        """
        env_var_name = secret_name.upper().replace("-", "_").replace("/", "_")
        env_value = os.getenv(env_var_name)

        if env_value:
            try:
                return json.loads(env_value)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse environment variable {env_var_name} as JSON")
                return {"raw_value": env_value}

        return None

    def invalidate_cache(self, secret_name: Optional[str] = None):
        """
        Invalidate cache for a specific secret or all secrets.

        Args:
            secret_name: If provided, only invalidate this secret. If None, clear all.
        """
        if secret_name:
            self._cache.pop(secret_name, None)
            logger.debug(f"Invalidated cache for secret: {secret_name}")
        else:
            self._cache.clear()
            logger.debug("Cleared entire secrets cache")


# Singleton instance for app-wide use
_secrets_manager: Optional[SecretsManagerClient] = None


def get_secrets_manager(
    region_name: str = "us-east-1", use_env_fallback: bool = True
) -> SecretsManagerClient:
    """
    Get or create the singleton SecretsManagerClient.

    Args:
        region_name: AWS region
        use_env_fallback: Fall back to env vars

    Returns:
        SecretsManagerClient singleton.
    """
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManagerClient(region_name, use_env_fallback)
    return _secrets_manager
