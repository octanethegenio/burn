from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import auth, launcher, main, store


class LauncherTests(unittest.TestCase):
    def test_existing_server_opens_browser_and_exits(self) -> None:
        with (
            patch.object(sys, "argv", ["burn"]),
            patch.object(launcher, "_burn_is_ready", return_value=True),
            patch.object(launcher.webbrowser, "open", return_value=True) as open_browser,
        ):
            launcher.main()

        open_browser.assert_called_once_with("http://127.0.0.1:8765/", new=2)


class PlatformPathTests(unittest.TestCase):
    def test_cursor_state_paths(self) -> None:
        home = Path("/home/person")
        self.assertEqual(
            auth._state_db_path(platform="darwin", home=home, env={}),
            home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb",
        )
        self.assertEqual(
            auth._state_db_path(
                platform="win32",
                home=home,
                env={"APPDATA": "C:/Users/person/AppData/Roaming"},
            ),
            Path("C:/Users/person/AppData/Roaming/Cursor/User/globalStorage/state.vscdb"),
        )
        self.assertEqual(
            auth._state_db_path(
                platform="linux", home=home, env={"XDG_CONFIG_HOME": "/config"}
            ),
            Path("/config/Cursor/User/globalStorage/state.vscdb"),
        )

    def test_cache_paths(self) -> None:
        home = Path("/home/person")
        self.assertEqual(
            store._data_dir(platform="darwin", home=home, env={}),
            home / "Library/Application Support/Burn",
        )
        self.assertEqual(
            store._data_dir(
                platform="win32",
                home=home,
                env={"LOCALAPPDATA": "C:/Users/person/AppData/Local"},
            ),
            Path("C:/Users/person/AppData/Local/Burn"),
        )
        self.assertEqual(
            store._data_dir(platform="linux", home=home, env={"XDG_DATA_HOME": "/data"}),
            Path("/data/burn"),
        )


class ModelMatchingTests(unittest.TestCase):
    def test_effort_alias_matches_aggregate(self) -> None:
        matched = main._match_event_to_agg(
            "grok-4.5-high",
            ["cursor-grok-4.5-xhigh", "claude-4.5-high"],
        )
        self.assertEqual(matched, "cursor-grok-4.5-xhigh")

    def test_event_id_has_no_account_identifier(self) -> None:
        event = {
            "timestamp": 123,
            "model": "model-a",
            "chargedCents": 1.5,
            "owningUser": "private-user-id",
        }
        event_id = main._event_id(event, 0)
        self.assertEqual(len(event_id), 32)
        self.assertNotIn("private-user-id", event_id)


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_dir = store.DATA_DIR
        self.original_db_path = store.DB_PATH
        self.original_legacy_path = store.LEGACY_DB_PATH
        self.original_migrate_legacy = store.MIGRATE_LEGACY
        store.DATA_DIR = Path(self.temp_dir.name)
        store.DB_PATH = store.DATA_DIR / "burn.db"
        store.LEGACY_DB_PATH = store.DATA_DIR / "legacy.db"
        store.MIGRATE_LEGACY = False

    def tearDown(self) -> None:
        store.DATA_DIR = self.original_data_dir
        store.DB_PATH = self.original_db_path
        store.LEGACY_DB_PATH = self.original_legacy_path
        store.MIGRATE_LEGACY = self.original_migrate_legacy
        self.temp_dir.cleanup()

    def test_old_sensitive_event_schema_is_cleared(self) -> None:
        with sqlite3.connect(store.DB_PATH) as con:
            con.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES (
                  'account',
                  '{"email":"person@example.com","sub":"secret","user_id":42}'
                );
                CREATE TABLE events (
                  id TEXT PRIMARY KEY,
                  ts_ms INTEGER NOT NULL,
                  model TEXT NOT NULL,
                  kind TEXT,
                  cost_cents REAL NOT NULL,
                  input_tokens INTEGER NOT NULL,
                  output_tokens INTEGER NOT NULL,
                  cache_read_tokens INTEGER NOT NULL,
                  cache_write_tokens INTEGER NOT NULL,
                  is_chargeable INTEGER,
                  raw_json TEXT NOT NULL
                );
                INSERT INTO events VALUES ('user:secret', 1, 'm', NULL, 0, 0, 0, 0, 0, 0, '{}');
                """
            )

        store.init_db()

        self.assertEqual(store.count_events(), 0)
        self.assertEqual(store.get_meta("account"), {"email": "person@example.com"})
        with store.connect() as con:
            columns = {row["name"] for row in con.execute("PRAGMA table_info(events)")}
        self.assertNotIn("raw_json", columns)

    def test_failed_snapshot_rolls_back(self) -> None:
        store.init_db()
        model = {
            "model": "model-a",
            "input_tokens": 1,
            "output_tokens": 2,
            "cache_read_tokens": 3,
            "cache_write_tokens": 4,
            "cost_cents": 5,
            "request_count": 1,
        }
        event = {
            "id": "event-a",
            "ts_ms": 1,
            "model": "model-a",
            "kind": "chat",
            "cost_cents": 5,
            "input_tokens": 1,
            "output_tokens": 2,
        }
        store.replace_snapshot([model], [event], {"email": "a@example.com"}, {"start": "a"})

        with self.assertRaises(sqlite3.IntegrityError):
            store.replace_snapshot(
                [{**model, "model": "duplicate"}, {**model, "model": "duplicate"}],
                [],
                {"email": "b@example.com"},
                {"start": "b"},
            )

        self.assertEqual([row["model"] for row in store.list_models()], ["model-a"])
        self.assertEqual([row["id"] for row in store.list_events()], ["event-a"])
        self.assertEqual(store.get_meta("account"), {"email": "a@example.com"})


if __name__ == "__main__":
    unittest.main()
