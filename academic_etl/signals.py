from django.db.backends.signals import connection_created
from django.db.utils import OperationalError
from django.dispatch import receiver


@receiver(connection_created)
def configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA busy_timeout=30000")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except OperationalError:
            # Another process may briefly own the SQLite write lock. The
            # connection remains usable and will inherit WAL once that clears.
            pass
