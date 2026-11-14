from __future__ import annotations


class StoredWorldMismatchException(Exception):
    pass


class WorldSessionEndedException(Exception):
    pass


class WorldSessionStillOpenException(Exception):
    pass
