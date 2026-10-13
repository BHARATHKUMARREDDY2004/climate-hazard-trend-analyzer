import time

import mongomock
import pytest

from app.storage import ANALYSES, DAILY, MongoStore, TinyStore


@pytest.fixture(params=["tinydb", "mongodb"])
def any_store(request, tmp_path):
    if request.param == "tinydb":
        store = TinyStore(tmp_path)
        yield store
        store.close()
    else:
        yield MongoStore("mongodb://unused", "test", client=mongomock.MongoClient())


def test_round_trip_and_upsert(any_store):
    any_store.put_many(DAILY, [{"_id": "a", "tmax": [1.0, None]}, {"_id": "b", "tmax": [2.0]}])
    any_store.put_many(DAILY, [{"_id": "a", "tmax": [9.0]}])

    assert any_store.get(DAILY, "a")["tmax"] == [9.0]
    assert any_store.get(DAILY, "missing") is None
    found = any_store.get_many(DAILY, ["a", "b", "c"])
    assert sorted(d["_id"] for d in found) == ["a", "b"]


def test_expired_documents_are_not_returned(any_store):
    now = time.time()
    any_store.put_many(
        ANALYSES,
        [{"_id": "old", "expires_at": now - 5}, {"_id": "new", "expires_at": now + 60}],
    )
    assert any_store.get(ANALYSES, "old") is None
    assert any_store.get(ANALYSES, "new")["_id"] == "new"


def test_tinydb_survives_a_restart(tmp_path):
    first = TinyStore(tmp_path)
    first.put_many(DAILY, [{"_id": "a", "year": 1999}])
    first.close()
    second = TinyStore(tmp_path)
    assert second.get(DAILY, "a")["year"] == 1999
    second.close()
