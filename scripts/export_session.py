#!/usr/bin/env python3
"""
Export Session to Markdown Archive

Exports a single OpenCode session as a human-readable markdown file.
Used before merge operations to preserve conversation history outside the database.

Usage:
    python3 export_session.py <session_id> <db_path> [--output-dir <dir>]
"""

import sqlite3
import json
import os
import sys
import re
from datetime import datetime


def get_connection(db_path):
    """Get database connection with safety settings."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def sanitize_filename(name):
    """Convert session title to safe filename."""
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s]+", "_", name)
    return name[:100]


def export_session(session_id, db_path, output_dir=None):
    """Export a single session to markdown."""
    if output_dir is None:
        output_dir = os.path.expanduser("~/.local/share/session-merge/archives/")

    os.makedirs(output_dir, exist_ok=True)

    conn = get_connection(db_path)

    # Get session info
    session = conn.execute(
        "SELECT * FROM session WHERE id = ?", (session_id,)
    ).fetchone()

    if not session:
        raise ValueError(f"Session not found: {session_id}")

    # Get messages
    messages = conn.execute(
        "SELECT * FROM message WHERE session_id = ? ORDER BY time_created",
        (session_id,),
    ).fetchall()

    # Build markdown
    lines = []
    lines.append(f"# {session['title']}")
    lines.append("")
    lines.append(f"**Session ID:** `{session['id']}`")
    lines.append(
        f"**Created:** {datetime.fromtimestamp(session['time_created'] / 1000).isoformat()}"
    )
    lines.append(
        f"**Updated:** {datetime.fromtimestamp(session['time_updated'] / 1000).isoformat()}"
    )
    lines.append(f"**Messages:** {len(messages)}")
    if session["share_url"]:
        lines.append(f"**Share URL:** {session['share_url']}")
    if session["summary_diffs"]:
        try:
            diffs = json.loads(session["summary_diffs"])
            lines.append(f"**Files changed:** {len(diffs)}")
            for d in diffs:
                lines.append(
                    f"  - `{d['path']}` (+{d.get('additions', 0)} -{d.get('deletions', 0)})"
                )
        except:
            pass
    lines.append("")
    lines.append("---")
    lines.append("")

    for msg in messages:
        try:
            msg_data = json.loads(msg["data"])
        except:
            continue

        role = msg_data.get("role", "unknown")
        timestamp = datetime.fromtimestamp(msg["time_created"] / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Get parts
        parts = conn.execute(
            "SELECT * FROM part WHERE message_id = ? ORDER BY time_created",
            (msg["id"],),
        ).fetchall()

        for part in parts:
            try:
                part_data = json.loads(part["data"])
            except:
                continue

            part_type = part_data.get("type", "")

            if part_type == "text":
                text = part_data.get("text", "")
                if text.strip():
                    lines.append(f"### [{role.upper()}] {timestamp}")
                    lines.append("")
                    lines.append(text)
                    lines.append("")

            elif part_type == "tool-use":
                tool_name = part_data.get("name", "unknown")
                tool_input = part_data.get("input", {})
                lines.append(f"### [TOOL CALL] {tool_name}")
                lines.append("")
                if tool_input:
                    if "command" in tool_input:
                        lines.append(f"```bash")
                        lines.append(tool_input["command"])
                        lines.append(f"```")
                    elif "filePath" in tool_input:
                        lines.append(f"File: `{tool_input['filePath']}`")
                    else:
                        lines.append(f"```json")
                        lines.append(json.dumps(tool_input, indent=2))
                        lines.append(f"```")
                lines.append("")

            elif part_type == "tool-result":
                output = str(part_data.get("output", ""))
                if output.strip():
                    lines.append(f"### [TOOL RESULT]")
                    lines.append("")
                    lines.append(f"```")
                    lines.append(output[:500])
                    if len(output) > 500:
                        lines.append(f"... (truncated, {len(output)} chars total)")
                    lines.append(f"```")
                    lines.append("")

            elif part_type == "reasoning":
                text = part_data.get("text", "")
                if text.strip():
                    lines.append(f"### [REASONING]")
                    lines.append("")
                    lines.append(f"> {text}")
                    lines.append("")

    # Write file
    filename = f"{session['id']}_{sanitize_filename(session['title'])}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    conn.close()

    return filepath


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Export OpenCode session to markdown")
    parser.add_argument("session_id", help="Session ID to export")
    parser.add_argument("db_path", help="Path to OpenCode SQLite database")
    parser.add_argument("--output-dir", help="Output directory for archives")
    parser.add_argument("--all", action="store_true", help="Export all sessions")
    args = parser.parse_args()

    try:
        if args.all:
            conn = get_connection(args.db_path)
            sessions = conn.execute(
                "SELECT id FROM session WHERE time_archived IS NULL"
            ).fetchall()
            conn.close()

            exported = 0
            for row in sessions:
                try:
                    filepath = export_session(row["id"], args.db_path, args.output_dir)
                    print(f"Exported: {filepath}")
                    exported += 1
                except Exception as e:
                    print(f"Failed to export {row['id']}: {e}", file=sys.stderr)

            print(f"\nExported {exported}/{len(sessions)} sessions")
        else:
            filepath = export_session(args.session_id, args.db_path, args.output_dir)
            print(f"Exported: {filepath}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
