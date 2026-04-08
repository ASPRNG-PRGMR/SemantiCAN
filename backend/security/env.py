import os
from dotenv import load_dotenv

load_dotenv()


def get_secret(name: str, default=None):
    """
    Returns the value of environment variable `name`.
    Returns `default` (None by default) if not set.

    Callers are responsible for deciding whether a missing secret is fatal.
    Fix: no longer raises — allows advisor.py fallback logic to work.
    """
    return os.getenv(name, default)
