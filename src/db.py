"""Postgres connection helper + the similarity search query."""

import psycopg2

from config import DB_PARAMS


def get_connection():
    """Open a connection to the Postgres database holding audi_doc.

    The only place in the project that knows a database exists is this file.
    Callers use it as a context manager:

        with get_connection() as conn, conn.cursor() as cur:
            ...
    """
    return psycopg2.connect(**DB_PARAMS)
