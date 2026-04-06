#!/usr/bin/env python3
"""
Test suite for Session Merge — Merge Engine

Tests:
- UUID remapping (no duplicate IDs)
- Message ordering (APPEND with separator)
- Merge summary injection
- Soft-delete (time_archived, not DELETE)
- Share URL transfer
- Backup creation
- Rollback on failure
- Database integrity
"""

import sqlite3
import json
import os
import sys
import tempfile
import time
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from merge_sessions import SessionMerger, MergeError
from find_candidates import get_connection, auto_create_indexes


def create_test_db():
    """Create a test database with sessions for merge testing."""
    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.executescript("""
        CREATE TABLE project (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL,
            time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL
        );
        CREATE TABLE session (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, parent_id TEXT,
            slug TEXT NOT NULL, directory TEXT NOT NULL, title TEXT NOT NULL,
            version TEXT NOT NULL, share_url TEXT, summary_additions INTEGER,
            summary_deletions INTEGER, summary_files INTEGER, summary_diffs TEXT,
            revert TEXT, permission TEXT, time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL, time_compacting INTEGER,
            time_archived INTEGER, workspace_id TEXT,
            FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
        );
        CREATE TABLE message (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
            data TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES session(id) ON DELETE CASCADE
        );
        CREATE TABLE part (
            id TEXT PRIMARY KEY, message_id TEXT NOT NULL, session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
            data TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES message(id) ON DELETE CASCADE
        );
        CREATE TABLE todo (
            session_id TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL,
            priority TEXT NOT NULL, position INTEGER NOT NULL,
            time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
            PRIMARY KEY (session_id, position)
        );
        CREATE TABLE session_share (
            session_id TEXT PRIMARY KEY, id TEXT NOT NULL, secret TEXT NOT NULL,
            url TEXT NOT NULL, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL
        );
    """)

    now = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO project (id, name, path, time_created, time_updated) VALUES (?, ?, ?, ?, ?)",
        ("global", "global", "/test", now, now),
    )

    # Target session (long)
    conn.execute(
        """INSERT INTO session (id, project_id, parent_id, slug, directory, title, version,
           time_created, time_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "ses_target",
            "global",
            None,
            "target",
            "/test",
            "Target Session",
            "1.0",
            now - 10000,
            now,
        ),
    )
    for i in range(10):
        msg_id = f"msg_target_{i}"
        msg_data = json.dumps(
            {"role": "user" if i % 2 == 0 else "assistant", "time": now + i * 1000}
        )
        conn.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (msg_id, "ses_target", now + i * 1000, now + i * 1000, msg_data),
        )
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"part_{msg_id}",
                msg_id,
                "ses_target",
                now + i * 1000,
                now + i * 1000,
                json.dumps({"type": "text", "text": f"Target message {i}"}),
            ),
        )

    # Source session 1 (short)
    conn.execute(
        """INSERT INTO session (id, project_id, parent_id, slug, directory, title, version,
           share_url, time_created, time_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "ses_source1",
            "global",
            None,
            "source1",
            "/test",
            "Source Session 1",
            "1.0",
            "https://opncd.ai/share/ABC123",
            now - 5000,
            now - 1000,
        ),
    )
    for i in range(3):
        msg_id = f"msg_source1_{i}"
        msg_data = json.dumps({"role": "user", "time": now + i * 1000})
        conn.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (msg_id, "ses_source1", now + i * 1000, now + i * 1000, msg_data),
        )
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"part_{msg_id}",
                msg_id,
                "ses_source1",
                now + i * 1000,
                now + i * 1000,
                json.dumps({"type": "text", "text": f"Source 1 message {i}"}),
            ),
        )
    # Add session_share
    conn.execute(
        "INSERT INTO session_share (session_id, id, secret, url, time_created, time_updated) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "ses_source1",
            "share_1",
            "secret_1",
            "https://opncd.ai/share/ABC123",
            now - 5000,
            now - 1000,
        ),
    )

    # Source session 2 (short)
    conn.execute(
        """INSERT INTO session (id, project_id, parent_id, slug, directory, title, version,
           time_created, time_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "ses_source2",
            "global",
            None,
            "source2",
            "/test",
            "Source Session 2",
            "1.0",
            now - 3000,
            now - 500,
        ),
    )
    for i in range(2):
        msg_id = f"msg_source2_{i}"
        msg_data = json.dumps({"role": "user", "time": now + i * 1000})
        conn.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (msg_id, "ses_source2", now + i * 1000, now + i * 1000, msg_data),
        )
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"part_{msg_id}",
                msg_id,
                "ses_source2",
                now + i * 1000,
                now + i * 1000,
                json.dumps({"type": "text", "text": f"Source 2 message {i}"}),
            ),
        )

    conn.commit()
    conn.close()
    return db_path


class TestUUIDRemapping(unittest.TestCase):
    """Test that all messages and parts get NEW UUIDs (NEVER reuse IDs)."""

    def setUp(self):
        self.db_path = create_test_db()
        self.merger = SessionMerger(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_no_duplicate_message_ids(self):
        """After merge, all message IDs must be unique."""
        self.merger.execute_merge("ses_target", ["ses_source1", "ses_source2"])

        conn = get_connection(self.db_path)
        all_ids = [r[0] for r in conn.execute("SELECT id FROM message").fetchall()]
        conn.close()

        self.assertEqual(
            len(all_ids), len(set(all_ids)), "Duplicate message IDs found!"
        )

    def test_no_duplicate_part_ids(self):
        """After merge, all part IDs must be unique."""
        self.merger.execute_merge("ses_target", ["ses_source1", "ses_source2"])

        conn = get_connection(self.db_path)
        all_ids = [r[0] for r in conn.execute("SELECT id FROM part").fetchall()]
        conn.close()

        self.assertEqual(len(all_ids), len(set(all_ids)), "Duplicate part IDs found!")

    def test_source_ids_not_reused(self):
        """Original source message IDs should NOT appear in target session."""
        conn = get_connection(self.db_path)
        source_msg_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM message WHERE session_id = 'ses_source1'"
            ).fetchall()
        ]
        conn.close()

        self.merger.execute_merge("ses_target", ["ses_source1"])

        conn = get_connection(self.db_path)
        target_msg_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM message WHERE session_id = 'ses_target'"
            ).fetchall()
        ]
        conn.close()

        # None of the original source IDs should be in target
        for sid in source_msg_ids:
            self.assertNotIn(sid, target_msg_ids, f"Source ID {sid} was reused!")


class TestMessageOrdering(unittest.TestCase):
    """Test APPEND strategy with separator messages."""

    def setUp(self):
        self.db_path = create_test_db()
        self.merger = SessionMerger(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_separator_messages_inserted(self):
        """Each source session should have a separator before its messages."""
        self.merger.execute_merge("ses_target", ["ses_source1", "ses_source2"])

        conn = get_connection(self.db_path)
        separators = conn.execute(
            """SELECT COUNT(*) FROM part p
               JOIN message m ON p.message_id = m.id
               WHERE m.session_id = 'ses_target'
               AND p.data LIKE '%MERGED FROM%'"""
        ).fetchone()[0]
        conn.close()

        self.assertEqual(separators, 2, "Expected 2 separator messages")

    def test_merge_summary_injected(self):
        """A SYSTEM merge summary message should be in target."""
        self.merger.execute_merge("ses_target", ["ses_source1", "ses_source2"])

        conn = get_connection(self.db_path)
        summary = conn.execute(
            """SELECT COUNT(*) FROM part p
               JOIN message m ON p.message_id = m.id
               WHERE m.session_id = 'ses_target'
               AND p.data LIKE '%Session Merge Summary%'"""
        ).fetchone()[0]
        conn.close()

        self.assertGreater(summary, 0, "Merge summary not found")


class TestSoftDelete(unittest.TestCase):
    """Test that sessions are soft-deleted (time_archived), not hard-deleted."""

    def setUp(self):
        self.db_path = create_test_db()
        self.merger = SessionMerger(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_source_sessions_archived_not_deleted(self):
        """Source sessions should have time_archived set, not be deleted."""
        self.merger.execute_merge("ses_target", ["ses_source1", "ses_source2"])

        conn = get_connection(self.db_path)

        for sid in ["ses_source1", "ses_source2"]:
            row = conn.execute(
                "SELECT time_archived FROM session WHERE id = ?", (sid,)
            ).fetchone()
            self.assertIsNotNone(row, f"Session {sid} was deleted instead of archived!")
            self.assertIsNotNone(row["time_archived"], f"Session {sid} not archived!")

        conn.close()

    def test_target_session_not_archived(self):
        """Target session should NOT be archived."""
        self.merger.execute_merge("ses_target", ["ses_source1"])

        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT time_archived FROM session WHERE id = 'ses_target'"
        ).fetchone()
        conn.close()

        self.assertIsNone(row["time_archived"], "Target session was archived!")


class TestShareURLTransfer(unittest.TestCase):
    """Test share URL transfer from source to target."""

    def setUp(self):
        self.db_path = create_test_db()
        self.merger = SessionMerger(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_share_url_transferred(self):
        """Share URL should move from source to target."""
        # Target has no share URL, source1 has one
        conn = get_connection(self.db_path)
        before = conn.execute(
            "SELECT share_url FROM session WHERE id = 'ses_target'"
        ).fetchone()
        self.assertIsNone(
            before["share_url"], "Target should not have share URL before merge"
        )
        conn.close()

        self.merger.execute_merge("ses_target", ["ses_source1"])

        conn = get_connection(self.db_path)
        after = conn.execute(
            "SELECT share_url FROM session WHERE id = 'ses_target'"
        ).fetchone()
        self.assertEqual(after["share_url"], "https://opncd.ai/share/ABC123")

        # session_share table should be updated
        share = conn.execute(
            "SELECT session_id FROM session_share WHERE url = 'https://opncd.ai/share/ABC123'"
        ).fetchone()
        self.assertEqual(share["session_id"], "ses_target")
        conn.close()


class TestBackupCreation(unittest.TestCase):
    """Test backup creation before merge."""

    def setUp(self):
        self.db_path = create_test_db()
        self.merger = SessionMerger(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_backup_created(self):
        """A backup should be created before merge."""
        self.merger.execute_merge("ses_target", ["ses_source1"])

        self.assertIsNotNone(self.merger.backup_path)
        self.assertTrue(os.path.exists(self.merger.backup_path))


class TestRollback(unittest.TestCase):
    """Test rollback on failure."""

    def setUp(self):
        self.db_path = create_test_db()
        self.merger = SessionMerger(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_merge_nonexistent_source_fails(self):
        """Merging a nonexistent source should fail cleanly."""
        with self.assertRaises(MergeError):
            self.merger.execute_merge("ses_target", ["ses_nonexistent"])

        # Database should still be intact
        conn = get_connection(self.db_path)
        target_msgs = conn.execute(
            "SELECT COUNT(*) FROM message WHERE session_id = 'ses_target'"
        ).fetchone()[0]
        conn.close()

        self.assertEqual(target_msgs, 10, "Target messages changed after failed merge!")


class TestDatabaseIntegrity(unittest.TestCase):
    """Test database integrity after merge."""

    def setUp(self):
        self.db_path = create_test_db()
        self.merger = SessionMerger(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_integrity_after_merge(self):
        """Database integrity check should pass after merge."""
        self.merger.execute_merge("ses_target", ["ses_source1", "ses_source2"])

        conn = get_connection(self.db_path)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()

        self.assertEqual(integrity, "ok")


class TestUndo(unittest.TestCase):
    """Test undo/restore from backup."""

    def setUp(self):
        self.db_path = create_test_db()
        self.merger = SessionMerger(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_undo_restores_database(self):
        """Undo should restore the database from backup."""
        # Get state before merge
        conn = get_connection(self.db_path)
        before_sessions = conn.execute("SELECT COUNT(*) FROM session").fetchone()[0]
        before_messages = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()

        # Merge
        self.merger.execute_merge("ses_target", ["ses_source1"])

        # Undo
        self.merger.undo_merge(self.merger.backup_path)

        # Verify restored
        conn = get_connection(self.db_path)
        after_sessions = conn.execute("SELECT COUNT(*) FROM session").fetchone()[0]
        after_messages = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        conn.close()

        self.assertEqual(before_sessions, after_sessions)
        self.assertEqual(before_messages, after_messages)


if __name__ == "__main__":
    unittest.main(verbosity=2)
