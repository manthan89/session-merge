#!/usr/bin/env python3
"""
Session Discovery and Clustering Engine

Scans OpenCode SQLite database, clusters related sessions by title similarity,
time proximity, and content overlap. Outputs merge candidates with health scores.

Usage:
    python3 find_candidates.py [db_path] [--json] [--verbose]
"""

import sqlite3
import json
import os
import sys
import time
import re
from collections import defaultdict
from difflib import SequenceMatcher


def get_config():
    """Load configuration from environment variables."""
    return {
        "short_threshold": int(os.environ.get("SESSION_MERGE_SHORT_THRESHOLD", 10)),
        "aggressiveness": os.environ.get("SESSION_MERGE_AGGRESSIVENESS", "balanced"),
        "title_threshold": float(os.environ.get("SESSION_MERGE_TITLE_THRESHOLD", 0.6)),
        "time_window": int(os.environ.get("SESSION_MERGE_TIME_WINDOW", 24)),
        "auto_confirm": os.environ.get("SESSION_MERGE_AUTO_CONFIRM", "false").lower()
        == "true",
        "tool": os.environ.get("SESSION_MERGE_TOOL", "auto"),
        "db_path": os.environ.get("SESSION_MERGE_DB_PATH", ""),
    }


def get_connection(db_path):
    """Get database connection with safety settings."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA wal_autocheckpoint=100;")
    return conn


def auto_create_indexes(conn):
    """Create indexes if they don't exist."""
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_session_parent ON session(parent_id);
        CREATE INDEX IF NOT EXISTS idx_session_created ON session(time_created);
        CREATE INDEX IF NOT EXISTS idx_session_updated ON session(time_updated);
        CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id, time_created);
        CREATE INDEX IF NOT EXISTS idx_part_message ON part(message_id, time_created);
        CREATE INDEX IF NOT EXISTS idx_part_session ON part(session_id);
    """)


def discover_sessions(conn):
    """Scan database and extract all sessions with metadata."""
    sessions = []

    rows = conn.execute("""
        SELECT s.*,
               (SELECT COUNT(*) FROM message WHERE session_id = s.id) as message_count,
               (SELECT COUNT(*) FROM part WHERE session_id = s.id) as part_count,
               (SELECT COUNT(*) FROM todo WHERE session_id = s.id) as todo_count
        FROM session s
        ORDER BY s.time_created
    """).fetchall()

    for row in rows:
        # Get first user message for content analysis
        first_user_msg = None
        msg_row = conn.execute(
            """
            SELECT data FROM message
            WHERE session_id = ? AND json_extract(data, '$.role') = 'user'
            ORDER BY time_created LIMIT 1
        """,
            (row["id"],),
        ).fetchone()

        if msg_row:
            try:
                msg_data = json.loads(msg_row["data"])
                content = msg_data.get("content", "")
                if isinstance(content, list):
                    first_user_msg = " ".join(
                        [c.get("text", "") for c in content if c.get("type") == "text"]
                    )
                else:
                    first_user_msg = str(content)
            except:
                pass

        session = {
            "id": row["id"],
            "title": row["title"],
            "parent_id": row["parent_id"],
            "project_id": row["project_id"],
            "message_count": row["message_count"],
            "part_count": row["part_count"],
            "todo_count": row["todo_count"],
            "created": row["time_created"],
            "updated": row["time_updated"],
            "archived": row["time_archived"] is not None,
            "has_share_url": row["share_url"] is not None,
            "share_url": row["share_url"],
            "has_diffs": row["summary_diffs"] is not None,
            "summary_diffs": row["summary_diffs"],
            "first_user_message": first_user_msg or "",
            "health_score": 0,
        }

        session["health_score"] = calculate_health_score(session)
        sessions.append(session)

    return sessions


def calculate_health_score(session):
    """Score session quality (0-100) for prioritization."""
    score = 0

    # Has meaningful title (not "New session - ...")
    if session["title"] and not session["title"].startswith("New session -"):
        score += 20

    # Message count (more = more valuable)
    if session["message_count"] >= 50:
        score += 25
    elif session["message_count"] >= 10:
        score += 15
    elif session["message_count"] >= 5:
        score += 10

    # Recency (newer = more relevant)
    now_ms = int(time.time() * 1000)
    days_old = (now_ms - session["updated"]) / (24 * 3600 * 1000)
    if days_old <= 1:
        score += 20
    elif days_old <= 7:
        score += 15
    elif days_old <= 30:
        score += 10

    # Has share URL (indicates importance)
    if session["has_share_url"]:
        score += 15

    # Has file changes (indicates real work)
    if session["has_diffs"]:
        score += 10

    return min(score, 100)


def extract_keywords(text):
    """Extract meaningful keywords from text."""
    if not text:
        return set()
    stop_words = {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "had",
        "her",
        "was",
        "one",
        "our",
        "out",
        "has",
        "have",
        "been",
        "this",
        "that",
        "with",
        "from",
        "they",
        "will",
        "each",
        "make",
        "like",
        "just",
        "over",
        "such",
        "more",
        "than",
        "them",
        "very",
        "when",
        "come",
        "could",
        "into",
        "time",
        "only",
        "its",
        "also",
        "after",
        "some",
        "then",
        "these",
        "two",
        "may",
        "most",
        "would",
        "other",
        "which",
        "their",
        "there",
        "about",
        "what",
        "said",
        "many",
        "does",
        "get",
        "way",
        "who",
        "did",
        "now",
        "how",
        "if",
        "or",
        "so",
        "up",
        "no",
        "my",
        "me",
        "we",
        "us",
        "it",
        "is",
        "am",
        "be",
        "to",
        "in",
        "on",
        "at",
        "by",
        "an",
        "a",
    }
    words = set(re.findall(r"\b[a-z]{3,}\b", text.lower()))
    return words - stop_words


def fuzzy_match(str1, str2):
    """Calculate fuzzy similarity between two strings."""
    if not str1 or not str2:
        return 0.0

    s1 = str1.lower().strip()
    s2 = str2.lower().strip()

    if s1 == s2:
        return 1.0

    # Substring match (one contains the other)
    if s1 in s2 or s2 in s1:
        return 0.85

    # Check if they share significant keywords
    kw1 = extract_keywords(s1)
    kw2 = extract_keywords(s2)
    if kw1 and kw2:
        overlap = len(kw1 & kw2)
        union = len(kw1 | kw2)
        if overlap >= 2 and union > 0:
            keyword_score = overlap / union
            # If keyword overlap is high, boost the similarity
            if keyword_score > 0.5:
                return max(0.7, keyword_score)

    return SequenceMatcher(None, s1, s2).ratio()


def keyword_overlap(text1, text2):
    """Calculate keyword overlap between two texts."""
    if not text1 or not text2:
        return 0.0

    words1 = extract_keywords(text1)
    words2 = extract_keywords(text2)

    if not words1 or not words2:
        return 0.0

    overlap = len(words1 & words2)
    union = len(words1 | words2)

    return overlap / union if union > 0 else 0.0


def calculate_similarity(session_a, session_b, config):
    """Calculate similarity score between two sessions.

    Requires BOTH title similarity AND time proximity to be considered related.
    This prevents chaining unrelated sessions together.
    """
    # Title similarity (required)
    title_score = fuzzy_match(session_a["title"], session_b["title"])
    if title_score < config["title_threshold"]:
        return 0.0  # Not similar enough by title — reject immediately

    # Time proximity (required)
    time_diff = abs(session_a["created"] - session_b["created"])
    time_window_ms = config["time_window"] * 3600 * 1000
    if time_diff > time_window_ms:
        return 0.0  # Too far apart in time — reject

    # Both passed — calculate weighted score
    time_score = 1.0 - (time_diff / time_window_ms)

    # Content similarity (bonus, not required)
    content_score = 0.0
    if session_a["first_user_message"] and session_b["first_user_message"]:
        content_score = keyword_overlap(
            session_a["first_user_message"], session_b["first_user_message"]
        )

    # Weighted: title 60%, time 25%, content 15%
    weighted = (title_score * 0.6) + (time_score * 0.25) + (content_score * 0.15)
    return weighted


def pre_filter_sessions(sessions, config):
    """Pre-filter sessions by project_id to reduce O(N²) scope.

    We do NOT filter by time window here — that's done in clustering.
    This just groups by project so we don't compare across projects.
    """
    # Filter out archived sessions
    active = [s for s in sessions if not s["archived"]]

    # Group by project_id
    by_project = defaultdict(list)
    for s in active:
        by_project[s["project_id"]].append(s)

    return by_project


def cluster_sessions(sessions_by_project, config):
    """Group related sessions into merge candidates.

    Uses a greedy approach: for each unprocessed session, find all sessions
    that are similar to it (title + time proximity). Each session belongs
    to exactly one cluster — no chaining.
    """
    clusters = []

    for project_id, sessions in sessions_by_project.items():
        processed = set()

        # Sort by health score (highest first) to prioritize important sessions
        sorted_sessions = sorted(
            sessions, key=lambda x: x["health_score"], reverse=True
        )

        for session in sorted_sessions:
            if session["id"] in processed:
                continue

            # Find sessions similar to THIS session (not chaining)
            related = [session]
            for other in sorted_sessions:
                if other["id"] in processed or other["id"] == session["id"]:
                    continue

                similarity = calculate_similarity(session, other, config)
                if similarity >= config["title_threshold"]:
                    related.append(other)

            if len(related) > 1:
                # Determine cluster topic
                topic = determine_topic(related)

                # Classify merge type
                merge_type = classify_merge_type(related, config)

                # Determine target (highest health score)
                target = max(related, key=lambda x: x["health_score"])

                cluster = {
                    "id": f"cluster_{len(clusters) + 1}",
                    "topic": topic,
                    "sessions": related,
                    "target": target,
                    "total_messages": sum(s["message_count"] for s in related),
                    "merge_type": merge_type,
                    "auto_merge": can_auto_merge(related, config),
                    "requires_confirmation": requires_confirmation(related, config),
                }
                clusters.append(cluster)
                processed.update(s["id"] for s in related)

    return clusters


def determine_topic(sessions):
    """Determine the common topic of a session cluster."""
    best = max(sessions, key=lambda x: x["health_score"])
    return best["title"]


def classify_merge_type(sessions, config):
    """Classify the type of merge needed."""
    short_count = sum(
        1 for s in sessions if s["message_count"] < config["short_threshold"]
    )
    long_count = sum(
        1 for s in sessions if s["message_count"] >= config["short_threshold"]
    )

    if long_count == 0:
        return "short_to_short"
    elif long_count == 1:
        return "short_to_long"
    else:
        return "long_to_long"


def can_auto_merge(sessions, config):
    """Determine if cluster can be auto-merged."""
    merge_type = classify_merge_type(sessions, config)
    return merge_type in ("short_to_short", "short_to_long")


def requires_confirmation(sessions, config):
    """Determine if cluster requires user confirmation."""
    return not can_auto_merge(sessions, config)


def detect_forks(sessions):
    """Detect fork relationships among sessions."""
    forks = []
    session_map = {s["id"]: s for s in sessions}

    for session in sessions:
        if session["parent_id"] and session["parent_id"] in session_map:
            parent = session_map[session["parent_id"]]
            forks.append({"fork": session, "parent": parent, "type": "simple_fork"})

    return forks


def format_session_line(session, config):
    """Format a session for display."""
    tag = "LONG" if session["message_count"] >= config["short_threshold"] else "SHORT"
    health = session["health_score"]
    return f"  [{tag}] {session['title']} ({session['message_count']} msgs, health: {health})"


def print_cluster_report(clusters, config, forks=None):
    """Print a human-readable cluster report."""
    print("\n" + "=" * 70)
    print("📋 Session Merge Analysis")
    print("=" * 70)

    if not clusters:
        print("\nNo merge candidates found.")
        return

    print(f"\nFound {len(clusters)} clusters of related sessions:\n")

    for cluster in clusters:
        print(
            f'Cluster: "{cluster["topic"]}" ({len(cluster["sessions"])} sessions, {cluster["total_messages"]} total messages)'
        )
        print(f"  Type: {cluster['merge_type']}")
        print(f"  Target: {cluster['target']['title']}")
        print(
            f"  Auto-merge: {'Yes' if cluster['auto_merge'] else 'No (requires confirmation)'}"
        )
        print()

        for session in sorted(
            cluster["sessions"], key=lambda x: x["health_score"], reverse=True
        ):
            line = format_session_line(session, config)
            if session["id"] == cluster["target"]["id"]:
                line += " ← TARGET"
            if session["parent_id"]:
                line += f" (fork of {session['parent_id'][:12]}...)"
            print(line)

        print()
        print("-" * 70)
        print()

    # Summary
    auto_clusters = [c for c in clusters if c["auto_merge"]]
    manual_clusters = [c for c in clusters if not c["auto_merge"]]

    print(f"Summary:")
    print(f"  Auto-merge candidates: {len(auto_clusters)} clusters")
    print(f"  Manual review needed: {len(manual_clusters)} clusters")
    print(f"  Total sessions involved: {sum(len(c['sessions']) for c in clusters)}")
    print(
        f"  Total messages to consolidate: {sum(c['total_messages'] for c in clusters)}"
    )

    if forks:
        print(f"\nFork relationships detected: {len(forks)}")
        for fork in forks[:5]:
            print(f"  {fork['fork']['title']} → {fork['parent']['title']}")
        if len(forks) > 5:
            print(f"  ... and {len(forks) - 5} more")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Discover and cluster related OpenCode sessions"
    )
    parser.add_argument("db_path", nargs="?", help="Path to OpenCode SQLite database")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    config = get_config()

    if args.db_path:
        config["db_path"] = args.db_path

    if not config["db_path"]:
        config["db_path"] = os.path.expanduser("~/.local/share/opencode/opencode.db")

    try:
        conn = get_connection(config["db_path"])
        auto_create_indexes(conn)

        sessions = discover_sessions(conn)
        sessions_by_project = pre_filter_sessions(sessions, config)
        clusters = cluster_sessions(sessions_by_project, config)
        forks = detect_forks(sessions)

        if args.json:
            output = {
                "clusters": clusters,
                "forks": forks,
                "total_sessions": len(sessions),
                "total_clusters": len(clusters),
            }
            print(json.dumps(output, indent=2))
        else:
            print_cluster_report(clusters, config, forks)

        conn.close()

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
