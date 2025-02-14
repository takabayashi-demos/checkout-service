"""Configuration for shipping options."""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class ShippingoptionsConfig:
    """Configuration for shipping options feature."""
    enabled: bool = True
    timeout_ms: int = int(os.getenv("CHECKOUT_SERVICE_TIMEOUT", "5000"))
    max_retries: int = 3
    batch_size: int = 100
    cache_ttl_seconds: int = 300
    allowed_regions: List[str] = field(default_factory=lambda: ["us-east-1", "us-west-2", "eu-west-1"])

    def validate(self) -> bool:
        """Validate configuration values."""
        if self.timeout_ms < 100:
            raise ValueError("Timeout must be >= 100ms")
        if self.max_retries < 0:
            raise ValueError("Max retries cannot be negative")
        if self.batch_size > 10000:
            raise ValueError("Batch size too large")
        return True


# Default configuration
DEFAULT_CONFIG = ShippingoptionsConfig()


# --- fix(api): prevent session expiry ---
"""Module for order confirmation in checkout-service."""
import logging
import time
from functools import lru_cache
from typing import Optional, Dict, List

logger = logging.getLogger("checkout-service.session")


class SessionHandler:
    """Handles session operations for checkout-service."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._cache = {}
        self._metrics = {"requests": 0, "errors": 0, "latency_sum": 0}
        logger.info(f"Initialized session handler")

