"""Pytest-wide configuration.

The multi-tenant isolation probes in test_isolation.py genuinely write to and
read from MongoDB (they seed a synthetic client_A fact and prove client_B can't
see it). They can only pass against a reachable database, so by default we skip
them and run the pure-logic suite — which is what CI does.

To run the DB probes (locally, or in a job with a real Atlas connection), set
RUN_DB_TESTS=1 in the environment. We key on this explicit flag, NOT on the mere
presence of MONGODB_URI, because config.Settings *requires* MONGODB_URI just to
import the app, so CI always has a (dummy) one set.
"""
import os

import pytest

# Legacy DB-dependent tests that pre-date the `@pytest.mark.db` marker, kept by
# name so the guard stays explicit. New DB tests should just use @pytest.mark.db.
_DB_DEPENDENT = {"test_cross_client_probe", "test_db_self_test"}


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "db: test needs a live MongoDB; skipped unless RUN_DB_TESTS=1 is set",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_DB_TESTS"):
        return  # operator opted in — a real Mongo is expected to be reachable
    skip_db = pytest.mark.skip(reason="needs live MongoDB; set RUN_DB_TESTS=1 to run")
    for item in items:
        if item.name in _DB_DEPENDENT or item.get_closest_marker("db"):
            item.add_marker(skip_db)
