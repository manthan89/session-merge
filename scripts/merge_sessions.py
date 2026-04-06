#!/usr/bin/env python3
"""
Session Merge Engine — Core merge execution with ALL safety checks.

Implements:
- UUID remapping for all messages and parts (NEVER reuse IDs)
- APPEND strategy with separator messages (NOT chronological interleaving)
- Merge summary injection as SYSTEM message
- Soft-delete ONLY (time_archived, never DELETE)
- SQLite concurrency safety (WAL, busy_timeout, foreign_keys)
- Share URL transfer
- Auto-create indexes
- Memory system integration
- Full transaction safety with rollback on ANY failure

Usage:
    python3 merge_sessions.py [options]

Options:
    --dry-run           Show what would be merged without executing
    --undo              Restore from latest backup
    --cluster <id>      Merge specific cluster by ID
    --target <id>       Specify target session ID
    --sources <id1,id2> Specify source session IDs to merge into target
    --force             Skip confirmation prompts
    --verbose           Show detailed output
"""

import sqlite3
import json
import os
import sys
import time
import uuid
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# Import find_candidates for discovery
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find_candidates import (
    get_config,
    get_connection,
    auto_create_indexes,
    discover_sessions,
    pre_filter_sessions,
    cluster_sessions,
    detect_forks,
    print_cluster_report,
)


BACKUP_DIR = os.path.expanduser("~/.local/share/session-merge/backups/")
ARCHIVE_DIR = os.path.expanduser("~/.local/share/session-merge/archives/")
LOG_FILE = os.path.expanduser("~/.local/share/session-merge/merge-history.log")
MEMORY_DIR = os.path.expanduser("~/.config/opencode/memory/sessions/")


class MergeError(Exception):
    """Raised when a merge operation fails."""

    pass


class SessionMerger:
    def __init__(self, db_path, config=None):
        self.db_path = db_path
        self.config = config or get_config()
        self.backup_path = None
        self.merged_sessions = []

    def log(self, message):
        """Log merge action."""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)

        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")

    def create_backup(self):
        """Create timestamped database backup."""
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_path = os.path.join(BACKUP_DIR, f"opencode.db.backup.{timestamp}")

        try:
            shutil.copy2(self.db_path, self.backup_path)
            self.log(f"Backup created: {self.backup_path}")
            return True
        except Exception as e:
            self.log(f"Backup failed: {e}")
            return False

    def pre_merge_checks(self, conn, target_id, source_ids):
        """Run all pre-merge safety checks."""
        # Verify target exists
        target = conn.execute(
            "SELECT * FROM session WHERE id = ?", (target_id,)
        ).fetchone()
        if not target:
            raise MergeError(f"Target session not found: {target_id}")

        # Verify sources exist
        for sid in source_ids:
            source = conn.execute(
                "SELECT * FROM session WHERE id = ?", (sid,)
            ).fetchone()
            if not source:
                raise MergeError(f"Source session not found: {sid}")
            if source["time_archived"] is not None:
                raise MergeError(f"Source session already archived: {sid}")

        # Check for file changes in sources
        for sid in source_ids:
            source = conn.execute(
                "SELECT title, summary_diffs FROM session WHERE id = ?", (sid,)
            ).fetchone()
            if source["summary_diffs"]:
                self.log(
                    f"WARNING: Source '{source['title']}' has file changes. "
                    "These will NOT be applied — only conversation history is merged."
                )

        return True

    def copy_messages(self, conn, source_id, target_id):
        """Copy messages and parts from source to target with NEW UUIDs.

        NEVER reuses existing message.id or part.id.
        Returns a map of old message_id -> new message_id.
        """
        message_map = {}

        # Copy messages
        messages = conn.execute(
            "SELECT * FROM message WHERE session_id = ? ORDER BY time_created",
            (source_id,),
        ).fetchall()

        for msg in messages:
            new_msg_id = str(uuid.uuid4())
            message_map[msg["id"]] = new_msg_id
            conn.execute(
                """INSERT INTO message (id, session_id, time_created, time_updated, data)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    new_msg_id,
                    target_id,
                    msg["time_created"],
                    msg["time_updated"],
                    msg["data"],
                ),
            )

        # Copy parts with remapped message IDs
        parts = conn.execute(
            "SELECT * FROM part WHERE session_id = ? ORDER BY time_created",
            (source_id,),
        ).fetchall()

        for part in parts:
            new_part_id = str(uuid.uuid4())
            new_msg_id = message_map[part["message_id"]]
            conn.execute(
                """INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    new_part_id,
                    new_msg_id,
                    target_id,
                    part["time_created"],
                    part["time_updated"],
                    part["data"],
                ),
            )

        return message_map

    def insert_separator(self, conn, target_id, source_title, msg_count):
        """Insert a separator message before merged content."""
        separator_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        separator_text = (
            f"\n--- MERGED FROM: {source_title} ({msg_count} messages) ---\n"
        )

        conn.execute(
            """INSERT INTO message (id, session_id, time_created, time_updated, data)
               VALUES (?, ?, ?, ?, ?)""",
            (
                separator_id,
                target_id,
                now_ms,
                now_ms,
                json.dumps({"role": "system", "time": now_ms}),
            ),
        )

        conn.execute(
            """INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                separator_id,
                target_id,
                now_ms,
                now_ms,
                json.dumps({"type": "text", "text": separator_text}),
            ),
        )

    def insert_merge_summary(self, conn, target_id, sources, backup_path):
        """Insert a SYSTEM merge summary message into target session."""
        summary_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)

        source_lines = []
        for s in sources:
            source_lines.append(f"- {s['title']} ({s['message_count']} messages)")

        summary_text = (
            f"Session Merge Summary:\n"
            f"Merged {len(sources)} sessions into this conversation.\n\n"
            f"Sources:\n" + "\n".join(source_lines) + f"\n\nBackup: {backup_path}\n"
            f"Time: {datetime.now().isoformat()}\n"
            f"Undo: python3 merge_sessions.py --undo --backup {backup_path}"
        )

        conn.execute(
            """INSERT INTO message (id, session_id, time_created, time_updated, data)
               VALUES (?, ?, ?, ?, ?)""",
            (
                summary_id,
                target_id,
                now_ms,
                now_ms,
                json.dumps({"role": "system", "time": now_ms}),
            ),
        )

        conn.execute(
            """INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                summary_id,
                target_id,
                now_ms,
                now_ms,
                json.dumps({"type": "text", "text": summary_text}),
            ),
        )

    def transfer_share_url(self, conn, target_id, source_id):
        """Transfer share URL from source to target if target doesn't have one."""
        target_share = conn.execute(
            "SELECT share_url FROM session WHERE id = ?", (target_id,)
        ).fetchone()

        if not target_share[0]:
            source_share = conn.execute(
                "SELECT share_url FROM session WHERE id = ?", (source_id,)
            ).fetchone()
            if source_share[0]:
                conn.execute(
                    "UPDATE session SET share_url = ? WHERE id = ?",
                    (source_share[0], target_id),
                )
                conn.execute(
                    "UPDATE session_share SET session_id = ? WHERE session_id = ?",
                    (target_id, source_id),
                )
                self.log(f"Share URL transferred from source to target")

    def soft_delete_session(self, conn, session_id):
        """Soft-delete a session by setting time_archived."""
        conn.execute(
            "UPDATE session SET time_archived = ? WHERE id = ?",
            (int(time.time()), session_id),
        )

    def post_merge_verification(self, conn, target_id, source_ids, backup_path):
        """Verify merge was successful."""
        # Verify merge summary exists
        summary_exists = conn.execute(
            """SELECT COUNT(*) FROM part p
               JOIN message m ON p.message_id = m.id
               WHERE m.session_id = ? AND p.data LIKE '%Session Merge Summary%'""",
            (target_id,),
        ).fetchone()[0]

        if summary_exists == 0:
            raise MergeError("Merge summary not found in target session")

        # Verify source sessions are archived
        for sid in source_ids:
            archived = conn.execute(
                "SELECT time_archived FROM session WHERE id = ?", (sid,)
            ).fetchone()
            if not archived or archived[0] is None:
                raise MergeError(f"Source session not archived: {sid}")

        # Verify database integrity
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise MergeError(f"Database integrity check failed: {integrity}")

        self.log("Post-merge verification passed")
        return True

    def update_memory_system(self, target_title, source_titles, backup_path):
        """Update OpenCode memory files if they exist."""
        if not os.path.exists(MEMORY_DIR):
            return

        try:
            # Write a merge note
            os.makedirs(MEMORY_DIR, exist_ok=True)
            merge_note_path = os.path.join(MEMORY_DIR, "merge-log.md")

            with open(merge_note_path, "a") as f:
                f.write(f"\n## {datetime.now().isoformat()}\n")
                f.write(
                    f"Merged {len(source_titles)} sessions into '{target_title}':\n"
                )
                for t in source_titles:
                    f.write(f"- {t}\n")
                f.write(f"Backup: {backup_path}\n")

            self.log(f"Memory system updated: {merge_note_path}")
        except Exception as e:
            self.log(f"WARNING: Could not update memory system: {e}")

    def log_merge_action(self, target_id, source_ids, backup_path, total_messages):
        """Log detailed merge action."""
        action = {
            "timestamp": datetime.now().isoformat(),
            "target": target_id,
            "sources": source_ids,
            "backup_path": backup_path,
            "total_messages": total_messages,
        }
        self.log(f"MERGE: {json.dumps(action)}")

    def execute_merge(self, target_id, source_ids, dry_run=False):
        """Execute merge for a set of source sessions into a target.

        Safety flow: backup → transaction → verify → commit → post-check → log
        """
        if dry_run:
            self.log(
                f"[DRY RUN] Would merge {len(source_ids)} sessions into {target_id}"
            )
            return True

        # Create backup
        if not self.create_backup():
            raise MergeError("Backup creation failed — aborting merge")

        conn = get_connection(self.db_path)

        try:
            # Auto-create indexes (outside transaction, uses executescript)
            auto_create_indexes(conn)

            # Close and reopen connection for clean transaction
            conn.close()
            conn = get_connection(self.db_path)

            conn.execute("BEGIN IMMEDIATE TRANSACTION")

            # Pre-merge checks
            self.pre_merge_checks(conn, target_id, source_ids)

            # Get source session info before merging
            sources_info = []
            for sid in source_ids:
                row = conn.execute(
                    "SELECT id, title FROM session WHERE id = ?",
                    (sid,),
                ).fetchone()
                msg_count = conn.execute(
                    "SELECT COUNT(*) FROM message WHERE session_id = ?", (sid,)
                ).fetchone()[0]
                sources_info.append(
                    {
                        "id": sid,
                        "title": row["title"],
                        "message_count": msg_count,
                    }
                )

            # Merge each source session
            total_merged_messages = 0
            for source in sources_info:
                sid = source["id"]

                # Insert separator
                self.insert_separator(
                    conn, target_id, source["title"], source["message_count"]
                )

                # Copy messages and parts with new UUIDs
                msg_map = self.copy_messages(conn, sid, target_id)
                total_merged_messages += source["message_count"]

                # Transfer share URL if source has one
                self.transfer_share_url(conn, target_id, sid)

                # Soft-delete source
                self.soft_delete_session(conn, sid)
                self.log(
                    f"Merged and archived: {source['title']} ({source['message_count']} msgs)"
                )

            # Insert merge summary
            self.insert_merge_summary(conn, target_id, sources_info, self.backup_path)

            # Update target session timestamp
            conn.execute(
                "UPDATE session SET time_updated = ? WHERE id = ?",
                (int(time.time() * 1000), target_id),
            )

            # Post-merge verification
            self.post_merge_verification(conn, target_id, source_ids, self.backup_path)

            conn.commit()

            # Update memory system
            self.update_memory_system(
                conn.execute(
                    "SELECT title FROM session WHERE id = ?", (target_id,)
                ).fetchone()["title"],
                [s["title"] for s in sources_info],
                self.backup_path,
            )

            # Log merge action
            self.log_merge_action(
                target_id, source_ids, self.backup_path, total_merged_messages
            )

            self.log(
                f"Merge completed: {total_merged_messages} messages from "
                f"{len(source_ids)} sessions merged into target"
            )

            return True

        except Exception as e:
            conn.rollback()
            self.log(f"Merge failed: {e}")
            raise MergeError(f"Merge failed: {e}")
        finally:
            conn.close()

    def undo_merge(self, backup_path=None):
        """Restore from backup."""
        if backup_path and os.path.exists(backup_path):
            restore_path = backup_path
        else:
            # Find latest backup
            os.makedirs(BACKUP_DIR, exist_ok=True)
            backups = sorted(Path(BACKUP_DIR).glob("opencode.db.backup.*"))
            if not backups:
                raise MergeError("No backups found")
            restore_path = str(backups[-1])

        if not os.path.exists(restore_path):
            raise MergeError(f"Backup not found: {restore_path}")

        # Verify backup integrity
        try:
            test_conn = sqlite3.connect(restore_path)
            integrity = test_conn.execute("PRAGMA integrity_check").fetchone()[0]
            test_conn.close()
            if integrity != "ok":
                raise MergeError(f"Backup database is corrupted: {integrity}")
        except Exception as e:
            raise MergeError(f"Backup verification failed: {e}")

        # Restore
        shutil.copy2(restore_path, self.db_path)

        # Verify restoration
        conn = get_connection(self.db_path)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if integrity != "ok":
            raise MergeError(f"Restored database is corrupted: {integrity}")

        self.log(f"Restored from backup: {restore_path}")
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Merge OpenCode sessions safely")
    parser.add_argument("db_path", nargs="?", help="Path to OpenCode SQLite database")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be merged"
    )
    parser.add_argument(
        "--undo", action="store_true", help="Restore from latest backup"
    )
    parser.add_argument("--backup", help="Path to specific backup for undo")
    parser.add_argument("--target", help="Target session ID")
    parser.add_argument("--sources", help="Comma-separated source session IDs")
    parser.add_argument("--cluster", help="Cluster ID from find_candidates")
    parser.add_argument("--force", action="store_true", help="Skip confirmation")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    config = get_config()

    if args.db_path:
        config["db_path"] = args.db_path

    if not config["db_path"]:
        config["db_path"] = os.path.expanduser("~/.local/share/opencode/opencode.db")

    merger = SessionMerger(config["db_path"], config)

    # Undo mode
    if args.undo:
        try:
            merger.undo_merge(args.backup)
            print("Undo completed successfully")
        except MergeError as e:
            print(f"Undo failed: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Merge mode
    if not args.target or not args.sources:
        # Run discovery
        try:
            conn = get_connection(config["db_path"])
            auto_create_indexes(conn)
            sessions = discover_sessions(conn)
            sessions_by_project = pre_filter_sessions(sessions, config)
            clusters = cluster_sessions(sessions_by_project, config)
            forks = detect_forks(sessions)
            print_cluster_report(clusters, config, forks)
            conn.close()

            if not clusters:
                print("\nNo merge candidates found.")
                return

            # Ask for confirmation
            if not args.force and not config["auto_confirm"]:
                response = input("\nProceed with auto-merges? [Y/n] ").strip().lower()
                if response in ("n", "no"):
                    print("Aborted.")
                    return

            # Execute auto-merges
            for cluster in clusters:
                if cluster["auto_merge"]:
                    target_id = cluster["target"]["id"]
                    source_ids = [
                        s["id"] for s in cluster["sessions"] if s["id"] != target_id
                    ]
                    try:
                        merger.execute_merge(
                            target_id, source_ids, dry_run=args.dry_run
                        )
                    except MergeError as e:
                        print(f"Merge failed for cluster {cluster['id']}: {e}")
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            if args.verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)
        return

    # Direct merge mode
    source_ids = [s.strip() for s in args.sources.split(",")]
    try:
        merger.execute_merge(args.target, source_ids, dry_run=args.dry_run)
    except MergeError as e:
        print(f"Merge failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
