#!/usr/bin/env python3
"""
Test suite for Session Merge — Clustering Engine

Tests:
- Title similarity matching
- Time proximity filtering
- Content overlap detection
- Cluster formation
- Health scoring
- Fork detection
"""

import sqlite3
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from find_candidates import (
    get_connection,
    auto_create_indexes,
    discover_sessions,
    pre_filter_sessions,
    cluster_sessions,
    detect_forks,
    fuzzy_match,
    keyword_overlap,
    calculate_similarity,
    calculate_health_score,
    classify_merge_type,
    can_auto_merge,
)


def create_test_db(sessions_data):
    """Create a temporary test database with given sessions."""
    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    # Create tables
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

    # Insert default project
    now = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO project (id, name, path, time_created, time_updated) VALUES (?, ?, ?, ?, ?)",
        ("global", "global", "/test", now, now),
    )

    # Insert sessions
    for s in sessions_data:
        conn.execute(
            """INSERT INTO session (id, project_id, parent_id, slug, directory, title, version,
               share_url, summary_diffs, time_created, time_updated, time_archived)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                s["id"],
                "global",
                s.get("parent_id"),
                s["title"].lower().replace(" ", "-"),
                "/test",
                s["title"],
                "1.0",
                s.get("share_url"),
                s.get("summary_diffs"),
                s["created"],
                s["updated"],
                int(time.time()) if s.get("archived") else None,
            ),
        )

        # Insert messages
        for i in range(s.get("message_count", 5)):
            msg_id = f"msg_{s['id']}_{i}"
            role = "user" if i % 2 == 0 else "assistant"
            content = (
                s.get("first_user_message", "test message")
                if role == "user"
                else "assistant response"
            )
            msg_data = json.dumps(
                {"role": role, "time": s["created"] + i * 1000, "content": content}
            )
            conn.execute(
                "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
                (
                    msg_id,
                    s["id"],
                    s["created"] + i * 1000,
                    s["created"] + i * 1000,
                    msg_data,
                ),
            )

            # Insert parts
            part_data = json.dumps({"type": "text", "text": content})
            conn.execute(
                "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    f"part_{msg_id}",
                    msg_id,
                    s["id"],
                    s["created"] + i * 1000,
                    s["created"] + i * 1000,
                    part_data,
                ),
            )

    conn.commit()
    conn.close()
    return db_path


class TestFuzzyMatch(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(fuzzy_match("Telegram bot", "Telegram bot"), 1.0)

    def test_case_insensitive(self):
        self.assertEqual(fuzzy_match("telegram bot", "TELEGRAM BOT"), 1.0)

    def test_substring_match(self):
        score = fuzzy_match("Telegram bot", "Fix Telegram bot")
        self.assertGreaterEqual(score, 0.8)

    def test_no_match(self):
        score = fuzzy_match("Telegram bot", "Content pipeline")
        self.assertLess(score, 0.5)

    def test_empty_strings(self):
        self.assertEqual(fuzzy_match("", "Telegram bot"), 0.0)
        self.assertEqual(fuzzy_match("Telegram bot", ""), 0.0)

    def test_keyword_overlap_boost(self):
        # Two titles with same keywords but different order
        score = fuzzy_match("Research video APIs", "Video APIs research")
        self.assertGreaterEqual(score, 0.7)


class TestKeywordOverlap(unittest.TestCase):
    def test_high_overlap(self):
        score = keyword_overlap(
            "fix telegram bot callback issue", "telegram bot callback data limit"
        )
        self.assertGreater(score, 0.3)

    def test_no_overlap(self):
        score = keyword_overlap("fix telegram bot", "content pipeline architecture")
        self.assertEqual(score, 0.0)

    def test_empty_strings(self):
        self.assertEqual(keyword_overlap("", "test"), 0.0)
        self.assertEqual(keyword_overlap("test", ""), 0.0)


class TestHealthScore(unittest.TestCase):
    def test_high_score_session(self):
        session = {
            "title": "Telegram bot",
            "message_count": 100,
            "updated": int(time.time() * 1000),
            "has_share_url": True,
            "has_diffs": True,
        }
        score = calculate_health_score(session)
        self.assertGreaterEqual(score, 80)

    def test_low_score_session(self):
        session = {
            "title": "New session - 2026-01-01",
            "message_count": 3,
            "updated": int(time.time() * 1000) - (60 * 24 * 3600 * 1000),  # 60 days ago
            "has_share_url": False,
            "has_diffs": False,
        }
        score = calculate_health_score(session)
        self.assertLessEqual(score, 30)


class TestClustering(unittest.TestCase):
    def setUp(self):
        now = int(time.time() * 1000)
        hour = 3600 * 1000

        self.sessions_data = [
            {
                "id": "ses_1",
                "title": "Telegram bot",
                "created": now - 2 * hour,
                "updated": now - hour,
                "message_count": 50,
                "first_user_message": "how to use telegram bot",
            },
            {
                "id": "ses_2",
                "title": "Fix telegram bot",
                "created": now - hour,
                "updated": now,
                "message_count": 5,
                "first_user_message": "fix telegram bot callback",
            },
            {
                "id": "ses_3",
                "title": "Content pipeline",
                "created": now - 2 * hour,
                "updated": now - hour,
                "message_count": 30,
                "first_user_message": "build content pipeline",
            },
            {
                "id": "ses_4",
                "title": "Content Pipeline Setup",
                "created": now - hour,
                "updated": now,
                "message_count": 20,
                "first_user_message": "setup content pipeline",
            },
        ]
        self.db_path = create_test_db(self.sessions_data)
        self.conn = get_connection(self.db_path)
        auto_create_indexes(self.conn)
        self.config = {
            "short_threshold": 10,
            "title_threshold": 0.6,
            "time_window": 24,
        }

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_clusters_found(self):
        sessions = discover_sessions(self.conn)
        by_project = pre_filter_sessions(sessions, self.config)
        clusters = cluster_sessions(by_project, self.config)
        # Should find at least 2 clusters (telegram + content)
        self.assertGreaterEqual(len(clusters), 2)

    def test_similar_titles_clustered(self):
        sessions = discover_sessions(self.conn)
        by_project = pre_filter_sessions(sessions, self.config)
        clusters = cluster_sessions(by_project, self.config)

        # Find telegram cluster
        telegram_cluster = None
        for c in clusters:
            if "telegram" in c["topic"].lower():
                telegram_cluster = c
                break

        self.assertIsNotNone(telegram_cluster)
        session_ids = {s["id"] for s in telegram_cluster["sessions"]}
        self.assertIn("ses_1", session_ids)
        self.assertIn("ses_2", session_ids)

    def test_different_topics_not_clustered(self):
        sessions = discover_sessions(self.conn)
        by_project = pre_filter_sessions(sessions, self.config)
        clusters = cluster_sessions(by_project, self.config)

        # Telegram and content should be in different clusters
        for cluster in clusters:
            session_ids = {s["id"] for s in cluster["sessions"]}
            has_telegram = "ses_1" in session_ids or "ses_2" in session_ids
            has_content = "ses_3" in session_ids or "ses_4" in session_ids
            self.assertFalse(has_telegram and has_content)


class TestForkDetection(unittest.TestCase):
    def test_simple_fork_detected(self):
        now = int(time.time() * 1000)
        sessions = [
            {
                "id": "parent",
                "parent_id": None,
                "title": "Main",
                "created": now - 1000,
                "updated": now,
                "message_count": 10,
                "first_user_message": "test",
                "has_share_url": False,
                "has_diffs": False,
                "archived": False,
                "health_score": 50,
            },
            {
                "id": "fork",
                "parent_id": "parent",
                "title": "Main fork",
                "created": now - 500,
                "updated": now,
                "message_count": 5,
                "first_user_message": "test",
                "has_share_url": False,
                "has_diffs": False,
                "archived": False,
                "health_score": 40,
            },
        ]
        forks = detect_forks(sessions)
        self.assertEqual(len(forks), 1)
        self.assertEqual(forks[0]["fork"]["id"], "fork")
        self.assertEqual(forks[0]["parent"]["id"], "parent")


class TestMergeTypeClassification(unittest.TestCase):
    def test_short_to_long(self):
        sessions = [
            {"message_count": 50},
            {"message_count": 5},
        ]
        config = {"short_threshold": 10}
        self.assertEqual(classify_merge_type(sessions, config), "short_to_long")
        self.assertTrue(can_auto_merge(sessions, config))

    def test_short_to_short(self):
        sessions = [
            {"message_count": 5},
            {"message_count": 3},
        ]
        config = {"short_threshold": 10}
        self.assertEqual(classify_merge_type(sessions, config), "short_to_short")
        self.assertTrue(can_auto_merge(sessions, config))

    def test_long_to_long(self):
        sessions = [
            {"message_count": 50},
            {"message_count": 30},
        ]
        config = {"short_threshold": 10}
        self.assertEqual(classify_merge_type(sessions, config), "long_to_long")
        self.assertFalse(can_auto_merge(sessions, config))


if __name__ == "__main__":
    unittest.main(verbosity=2)
