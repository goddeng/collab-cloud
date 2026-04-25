"""Tests for SQLite team store."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from store import TeamStore


def test_register_and_get():
    with tempfile.TemporaryDirectory() as tmp:
        s = TeamStore(f"{tmp}/x.db")
        s.register_team("t1", "secret-32-bytes-min-value-aaaa")
        assert s.get_secret("t1") == "secret-32-bytes-min-value-aaaa"
        assert s.get_secret("nope") is None
        s.close()


def test_upsert_overwrites():
    with tempfile.TemporaryDirectory() as tmp:
        s = TeamStore(f"{tmp}/x.db")
        s.register_team("t1", "old-secret-32-bytes-pad-pad-pad")
        s.register_team("t1", "new-secret-32-bytes-pad-pad-pad")
        assert s.get_secret("t1") == "new-secret-32-bytes-pad-pad-pad"
        assert len(s.list_teams()) == 1
        s.close()


def test_delete():
    with tempfile.TemporaryDirectory() as tmp:
        s = TeamStore(f"{tmp}/x.db")
        s.register_team("t1", "x" * 32)
        assert s.delete_team("t1") is True
        assert s.get_secret("t1") is None
        assert s.delete_team("missing") is False
        s.close()


def test_persistence_across_instances():
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/x.db"
        s1 = TeamStore(path)
        s1.register_team("t1", "x" * 32)
        s1.close()
        # 重新打开, 数据应该还在
        s2 = TeamStore(path)
        assert s2.get_secret("t1") == "x" * 32
        s2.close()


if __name__ == "__main__":
    test_register_and_get()
    test_upsert_overwrites()
    test_delete()
    test_persistence_across_instances()
    print("✅ all store tests passed")
