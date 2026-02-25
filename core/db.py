import psycopg2
from config.settings import DB_CONFIG


def get_connection():
    return psycopg2.connect(**DB_CONFIG)
