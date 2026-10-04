"""AWS Secrets Manager async client for the migration platform (architecture.md §14).

Provides runtime secret injection for DB credentials, Bedrock API keys, and
other sensitive config — replacing plaintext `.env` values in deployed containers.

Features
--------
- Async ``get_secret()`` with in-process TTL cache (avoids repeated API calls).
- Graceful fallback to environment variables when Secrets Manager is unreachable
  (supports local dev without AWS access).
- Typed helpers ``get_db_credentials()`` and ``get_aws_credentials()`` for the
  most common use-cases in the platform.
- Singleton factory ``get_secrets_manager()`` so all agents share one client.

Usage
-----
    from observability.secrets_manager import get_secrets_manager

    sm = get_secrets_manager()
    creds = await sm.get_db_credentials("capstone-prod/postgres-metadata")
    # -> {"username": "...", "password": "...", "host": "...", ...}
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Graceful degradation: boto3 is optional for local dev without AWS.
try:
    import boto3
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    ClientError = Exception  # type: ignore[assignment,misc]

# Module-level singleton.
_secrets_manager_instance: Optional["SecretsManagerClient"] = None


def get_secrets_manager(
    region_name: str | None = None,
    use_env_fallback: bool = True,
) -> "SecretsManagerClient":
    """Return the module-level singleton SecretsManagerClient."""
    global _secrets_manager_instance
    if _secrets_manager_instance is None:
        _secrets_manager_instance = SecretsManagerClient(
            region_name=region_name or os.getenv("AWS_REGION", "us-east-1"),
            use_env_fallback=use_env_fallback,
        )
    return _secrets_manager_instance


class SecretsManagerClient:
    """Async-friendly AWS Secrets Manager client with caching and env fallback.

    The client is *synchronous* internally (boto3 is sync) but exposes an
    ``async`` interface so it integrates cleanly with FastAPI and asyncio-based
    agent code.  The cache is an in-process dict with per-entry TTL.
    """

    # Default cache TTL: 5 minutes (secrets rarely change mid-run).
    _DEFAULT_CACHE_TTL_SECONDS = 300

    def __init__(
        self,
        region_name: str = "us-east-1",
        use_env_fallback: bool = True,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self.region_name = region_name
        self.use_env_fallback = use_env_fallback
        self.cache_ttl_seconds = cache_ttl_seconds

        # Cache: secret_id -> (value, expiry_timestamp)
        self._cache: dict[str, tuple[Any, float]] = {}

        self.client: Any = None
        if BOTO3_AVAILABLE:
            try:
                self.client = boto3.client("secretsmanager", region_name=region_name)
                logger.debug("SecretsManagerClient initialised (region=%s)", region_name)
            except Exception as exc:
                logger.warning("SecretsManagerClient init failed (%s) — env fallback only", exc)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def get_secret(
        self,
        secret_id: str,
        use_cache: bool = True,
    ) -> dict[str, Any] | str:
        """Retrieve and parse a secret by ID.

        Returns the secret as a dict (if JSON) or raw string.
        Falls back to environment variables on any error when
        ``use_env_fallback=True``.

        Args:
            secret_id: The Secrets Manager secret ID or ARN.
            use_cache:  Whether to return a cached value if available.

        Returns:
            Parsed secret dict or raw string value.

        Raises:
            RuntimeError: If the secret cannot be retrieved and no fallback exists.
        """
        # Check cache first.
        if use_cache:
            cached = self._get_cached(secret_id)
            if cached is not None:
                return cached

        # Try Secrets Manager.
        if self.client is not None:
            try:
                response = self.client.get_secret_value(SecretId=secret_id)
                raw = response.get("SecretString") or response.get("SecretBinary", b"").decode()
                value = self._parse_secret(raw)
                if use_cache:
                    self._set_cache(secret_id, value)
                return value
            except Exception as exc:
                logger.warning("Secrets Manager get_secret(%s) failed: %s", secret_id, exc)

        # Fallback: try to find a matching env var.
        if self.use_env_fallback:
            env_value = self._env_fallback(secret_id)
            if env_value is not None:
                logger.debug("Using env fallback for secret %s", secret_id)
                return env_value

        raise RuntimeError(
            f"Cannot retrieve secret '{secret_id}': "
            "Secrets Manager unavailable and no env fallback found."
        )

    async def get_db_credentials(self, secret_id: str) -> dict[str, Any]:
        """Retrieve database credentials dict from Secrets Manager.

        Expected secret shape::

            {
                "username": "...",
                "password": "...",
                "host": "...",
                "port": 5432,
                "database": "..."
            }

        Args:
            secret_id: Secrets Manager secret ID for the DB credentials.

        Returns:
            Dict with username, password, host, port, database keys.
        """
        secret = await self.get_secret(secret_id)
        if not isinstance(secret, dict):
            raise ValueError(f"Secret '{secret_id}' is not a JSON object — cannot use as DB credentials")
        return secret

    async def get_aws_credentials(self, secret_id: str) -> dict[str, Any]:
        """Retrieve AWS credentials dict from Secrets Manager.

        Expected secret shape::

            {
                "aws_access_key_id": "...",
                "aws_secret_access_key": "...",
                "aws_region": "us-east-1"
            }

        Args:
            secret_id: Secrets Manager secret ID for the AWS credentials.

        Returns:
            Dict with aws_access_key_id, aws_secret_access_key, aws_region keys.
        """
        secret = await self.get_secret(secret_id)
        if not isinstance(secret, dict):
            raise ValueError(f"Secret '{secret_id}' is not a JSON object — cannot use as AWS credentials")
        return secret

    async def get_secret_value(self, secret_id: str, key: str) -> str:
        """Retrieve a single string value from a JSON secret.

        Args:
            secret_id: Secrets Manager secret ID.
            key: Key within the JSON secret to return.

        Returns:
            String value for the given key.

        Raises:
            KeyError: If the key is not present in the secret.
        """
        secret = await self.get_secret(secret_id)
        if not isinstance(secret, dict):
            raise ValueError(f"Secret '{secret_id}' is not a JSON object")
        if key not in secret:
            raise KeyError(f"Key '{key}' not found in secret '{secret_id}'")
        return str(secret[key])

    def invalidate_cache(self, secret_id: str | None = None) -> None:
        """Invalidate a specific secret or the entire cache.

        Args:
            secret_id: If provided, invalidate only this secret; otherwise
                       clear the entire cache.
        """
        if secret_id is None:
            self._cache.clear()
            logger.debug("Secrets cache cleared")
        elif secret_id in self._cache:
            del self._cache[secret_id]
            logger.debug("Secrets cache invalidated for %s", secret_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_cached(self, secret_id: str) -> Any | None:
        """Return cached value if present and not expired."""
        if secret_id in self._cache:
            value, expiry = self._cache[secret_id]
            if time.monotonic() < expiry:
                return value
            # Expired — remove from cache.
            del self._cache[secret_id]
        return None

    def _set_cache(self, secret_id: str, value: Any) -> None:
        """Store a value in the cache with a TTL."""
        self._cache[secret_id] = (value, time.monotonic() + self.cache_ttl_seconds)

    @staticmethod
    def _parse_secret(raw: str) -> dict[str, Any] | str:
        """Parse a raw secret string — returns dict if JSON, else raw string."""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    @staticmethod
    def _env_fallback(secret_id: str) -> Any | None:
        """Try to find a matching environment variable for the given secret ID.

        Converts the secret ID to an env-var name by uppercasing and replacing
        non-alphanumeric characters with underscores.
        E.g. ``capstone-staging/db-credentials`` → ``CAPSTONE_STAGING_DB_CREDENTIALS``.
        """
        env_key = re.sub(r"[^A-Z0-9]", "_", secret_id.upper())
        raw = os.getenv(env_key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
