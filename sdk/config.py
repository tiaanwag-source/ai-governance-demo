# sdk/config.py

from dataclasses import dataclass
import os


@dataclass
class SDKConfig:
    """
    Basic configuration for the AI Governance SDK.
    For the demo we assume the API is running on localhost:8000.
    """
    api_base: str = "http://localhost:8000"
    timeout_seconds: float = 5.0


def load_config() -> SDKConfig:
    """
    Later you can make this read env vars.
    For now we just return a static config.
    """
    base = os.getenv("AI_GOV_API_BASE", "http://localhost:8000")
    timeout = float(os.getenv("AI_GOV_API_TIMEOUT", "5.0"))
    return SDKConfig(api_base=base, timeout_seconds=timeout)