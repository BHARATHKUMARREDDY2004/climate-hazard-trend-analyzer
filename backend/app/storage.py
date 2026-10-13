"""Document storage.

The service only needs three operations (get, get many, upsert many) so the
interface is kept that small. MongoDB is the intended backend. TinyDB is an
embedded document store used when MongoDB is not reachable, so the project
still runs with nothing but `pip install`.

Expiry: documents may carry `expires_at` (epoch seconds). Readers check it,
and on MongoDB a TTL index also removes the documents physically.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol

from .config import settings

log = logging.getLogger(__name__)

DAILY = "daily_weather"
ANALYSES = "analyses"
GEOCODE = "geocode_cache"
COLLECTIONS = (DAILY, ANALYSES, GEOCODE)


class Store(Protocol):
    name: str

    def get(self, collection: str, doc_id: str) -> dict | None: ...
    def get_many(self, collection: str, doc_ids: Iterable[str]) -> list[dict]: ...
    def put_many(self, collection: str, docs: list[dict]) -> None: ...
    def ping(self) -> bool: ...


def _alive(doc: dict | None) -> bool:
    if doc is None:
        return False
    expires = doc.get("expires_at")
    return expires is None or expires > time.time()


class MongoStore:
    name = "mongodb"

    def __init__(self, uri: str, db_name: str, client=None):
        from pymongo import MongoClient

        self._client = client or MongoClient(uri, serverSelectionTimeoutMS=1500)
        self._client.admin.command("ping")
        self._db = self._client[db_name]
        for coll in (ANALYSES, GEOCODE):
            self._db[coll].create_index("expires_at_date", expireAfterSeconds=0)
        self._db[DAILY].create_index([("cell", 1), ("year", 1)])

    def get(self, collection, doc_id):
        doc = self._db[collection].find_one({"_id": doc_id}, {"expires_at_date": 0})
        return doc if _alive(doc) else None

    def get_many(self, collection, doc_ids):
        cursor = self._db[collection].find(
            {"_id": {"$in": list(doc_ids)}}, {"expires_at_date": 0}
        )
        return [d for d in cursor if _alive(d)]

    def put_many(self, collection, docs):
        from pymongo import ReplaceOne

        ops = []
        for doc in docs:
            doc = dict(doc)
            if doc.get("expires_at") is not None:
                # TTL indexes only work on BSON dates.
                doc["expires_at_date"] = datetime.fromtimestamp(
                    doc["expires_at"], tz=timezone.utc
                )
            ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        if ops:
            self._db[collection].bulk_write(ops, ordered=False)

    def ping(self):
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            return False


class TinyStore:
    name = "tinydb"

    def __init__(self, directory: Path):
        from tinydb import TinyDB
        from tinydb.middlewares import CachingMiddleware
        from tinydb.storages import JSONStorage

        directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._dbs = {
            coll: TinyDB(
                directory / f"{coll}.json", storage=CachingMiddleware(JSONStorage)
            )
            for coll in COLLECTIONS
        }
        # TinyDB has no secondary indexes, so keep an _id -> doc_id map per collection.
        self._index = {
            coll: {d["_id"]: d.doc_id for d in db.all()} for coll, db in self._dbs.items()
        }

    def get(self, collection, doc_id):
        found = self.get_many(collection, [doc_id])
        return found[0] if found else None

    def get_many(self, collection, doc_ids):
        with self._lock:
            index, db = self._index[collection], self._dbs[collection]
            internal = [index[i] for i in doc_ids if i in index]
            docs = [dict(d) for d in db.get(doc_ids=internal)] if internal else []
        return [d for d in docs if _alive(d)]

    def put_many(self, collection, docs):
        if not docs:
            return
        with self._lock:
            index, db = self._index[collection], self._dbs[collection]
            stale = [index[d["_id"]] for d in docs if d["_id"] in index]
            if stale:
                db.remove(doc_ids=stale)
            new_ids = db.insert_multiple(docs)
            for doc, internal in zip(docs, new_ids):
                index[doc["_id"]] = internal
            db.storage.flush()

    def ping(self):
        return True

    def close(self):
        for db in self._dbs.values():
            db.close()


_store: Store | None = None


def init_store() -> Store:
    global _store
    backend = settings.storage_backend
    if backend in ("auto", "mongo"):
        try:
            _store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
            log.info("Using MongoDB at %s", settings.mongodb_uri.split("@")[-1])
            return _store
        except Exception as exc:
            if backend == "mongo":
                raise RuntimeError(f"MongoDB is not reachable: {exc}") from exc
            log.warning("MongoDB not reachable, falling back to TinyDB (%s)", exc)
    _store = TinyStore(settings.tinydb_dir)
    log.info("Using TinyDB files in %s", settings.tinydb_dir)
    return _store


def get_store() -> Store:
    return _store if _store is not None else init_store()


def set_store(store: Store | None) -> None:
    global _store
    _store = store
