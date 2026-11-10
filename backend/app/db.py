import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# read from .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)


def get_connection():
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.getenv("DB_SSLMODE", "require"),
        connect_timeout=10,
    )