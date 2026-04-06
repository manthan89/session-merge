---
name: session-merge
description: |
  Safely merge duplicate or related OpenCode sessions. Finds sessions with similar titles or topics,
  merges short sessions into long ones automatically, suggests merges for long sessions,
  and preserves all conversation history. Uses UUID remapping, soft-delete, transaction safety,
  and provides undo capability. Triggers on: "merge sessions", "clean up sessions",
  "consolidate sessions", "duplicate sessions", "combine sessions", "session cleanup",
  "too many sessions", "organize my sessions", "remove duplicate sessions".
allowed-tools:
  - Bash(python3 ~/.agents/skills/session-merge/scripts/*.py)
  - Bash(sqlite3 ~/.local/share/opencode/opencode.db *.timeout *)
  - Bash(cp ~/.local/share/opencode/opencode.db *)
---

# Session Merge

Safely consolidate duplicate or related OpenCode sessions. Preserves all conversation history,
transfers share URLs, and provides undo capability.

## Configuration

Preferences are set via environment variables (add to `~/.bashrc` or `~/.profile`):

```bash
# Trigger mode: "manual" | "command" | "auto-scan"
export SESSION_MERGE_TRIGGER="manual"

# Matching aggressiveness: "conservative" | "balanced" | "aggressive"
export SESSION_MERGE_AGGRESSIVENESS="balanced"

# Short session threshold (messages below this are "short")
export SESSION_MERGE_SHORT_THRESHOLD=10

# Title similarity threshold (0.0-1.0)
export SESSION_MERGE_TITLE_THRESHOLD=0.6

# Time proximity window (hours)
export SESSION_MERGE_TIME_WINDOW=24

# Auto-confirm merges (skip confirmation prompt)
export SESSION_MERGE_AUTO_CONFIRM="false"
```

### Defaults

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_MERGE_TRIGGER` | `manual` | How the skill activates |
| `SESSION_MERGE_AGGRESSIVENESS` | `balanced` | Matching strictness |
| `SESSION_MERGE_SHORT_THRESHOLD` | `10` | Messages below = "short" |
| `SESSION_MERGE_TITLE_THRESHOLD` | `0.6` | Title similarity cutoff |
| `SESSION_MERGE_TIME_WINDOW` | `24` | Hours for time proximity |
| `SESSION_MERGE_AUTO_CONFIRM` | `false` | Skip confirmation |

## Workflow

Follow this escalation pattern:

1. **Discover** — Scan database, cluster sessions by title + content + time
2. **Classify** — Separate short vs long sessions, identify merge candidates
3. **Suggest** — Present merge plan to user (auto-merge short, suggest long)
4. **Confirm** — Get user approval (skip if `SESSION_MERGE_AUTO_CONFIRM=true`)
5. **Execute** — Backup → export → merge → verify → report
6. **Undo** — Provide restore command if needed

### Step 1: Discover

Run the discovery script to find merge candidates:

```bash
python3 ~/.agents/skills/session-merge/scripts/find_candidates.py
```

This outputs a structured report of session clusters ready for merging.

### Step 2: Execute Merge

Run the merge script:

```bash
# Dry run (no changes)
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py --dry-run

# Execute merge (interactive)
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py

# Direct merge
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py --target <session_id> --sources <id1,id2>

# Undo last merge
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py --undo
```

### Step 3: Export Sessions (Optional)

Export sessions to markdown archives before merging:

```bash
# Export single session
python3 ~/.agents/skills/session-merge/scripts/export_session.py <session_id> <db_path>

# Export all active sessions
python3 ~/.agents/skills/session-merge/scripts/export_session.py --all <db_path>
```

## Merge Rules

| Source → Target | Short (<threshold msgs) | Long (≥threshold msgs) |
|-----------------|------------------------|------------------------|
| **Short** | ✅ Auto-merge into earliest | ✅ Auto-merge into long |
| **Long** | (N/A) | ⚠️ Suggest, require confirmation |

### Clustering Logic

Sessions are grouped into clusters when:

1. **Title match**: Fuzzy similarity ≥ `SESSION_MERGE_TITLE_THRESHOLD` (default 60%)
2. **Time proximity**: Created within `SESSION_MERGE_TIME_WINDOW` hours (default 24h)
3. **Content match**: First user message shares topic keywords (for unnamed sessions)

### Target Selection

Within each cluster, the merge target is chosen by:

1. **Longest session** (most messages) — primary rule
2. **Earliest session** (first created) — tiebreaker
3. **Has share URL** — bonus priority (avoids URL transfer)

## Safety Guarantees

**ALWAYS** (non-negotiable):

1. Create timestamped backup before any changes
2. Wrap all operations in SQLite transaction (all-or-nothing)
3. Transfer share URLs to target session before archiving source
4. Preserve parent-child relationships (re-parent children to target)
5. Add merge summary message to target session
6. Verify database integrity after merge
7. Warn about file changes (`summary_diffs`) before merging
8. Provide undo command with backup location
9. NEVER reuse message/part IDs — always generate new UUIDs
10. NEVER hard-delete sessions — soft-delete only (time_archived)

**NEVER**:

1. Delete sessions with share URLs without transferring first
2. Merge sessions across different projects without warning
3. Delete sessions without adding merge summary to target
4. Proceed if backup fails
5. Reuse existing message or part IDs

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Session has share URL | Transfer URL to target, then archive source |
| Session has file changes (`summary_diffs`) | Warn user, show diff summary, require explicit confirmation |
| Session has child sessions | Re-parent children to target before archiving parent |
| Session is currently active | Skip, warn user |
| Multiple long sessions in cluster | Present merge options, require explicit choice |
| All sessions in cluster are short | Merge into earliest session |
| Unnamed sessions (empty title) | Scan first user message for topic keywords |
| Merge fails mid-operation | Rollback via transaction, restore from backup |

## Output Format

### Discovery Output

```
📋 Session Merge Analysis

Found 3 clusters of related sessions:

Cluster 1: "telegram bot" (3 sessions, 495 total messages)
  Type: short_to_long
  Target: Telegram bot
  Auto-merge: Yes

  [LONG] Telegram bot (482 msgs, health: 85) ← TARGET
  [SHORT] Fixing telegram bot (5 msgs, health: 40)
  [SHORT] Stop Auto-Start Loop (8 msgs, health: 45)

Proceed with auto-merges? [Y/n]
```

### Merge Output

```
🔧 Merging Sessions

[1/3] Creating backup...
  ✅ /home/human/.local/share/session-merge/backups/opencode.db.backup.20260406_143022

[2/3] Merging 2 sessions into "Telegram bot"...
  ✅ Merged "Fixing telegram bot" (5 msgs)
  ✅ Merged "Stop Auto-Start Loop" (8 msgs)
  ✅ Added merge summary to target session
  ✅ Database integrity verified

[3/3] Updating memory system...
  ✅ Memory files updated

✨ Done! 2 sessions merged, 13 messages consolidated.

Undo: python3 merge_sessions.py --undo --backup /path/to/backup
```

## Installation

For detailed setup instructions, see [rules/install.md](rules/install.md).
For safety procedures and undo, see [rules/safety.md](rules/safety.md).
