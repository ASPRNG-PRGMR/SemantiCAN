import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_secret(name: str, default=None):
    return os.getenv(name, default)
