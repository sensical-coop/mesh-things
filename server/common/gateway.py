"""Public URL for the API"""
import os


def public_base_url() -> str:
    """Base URL for the API"""
    return os.environ.get("GATEWAY__PUBLIC_URL", "http://localhost").rstrip("/")
