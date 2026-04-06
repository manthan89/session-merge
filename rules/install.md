# Installation Guide

## Prerequisites

- Python 3.8+
- SQLite3 (included with Python)
- OpenCode installed (for skill integration)

## Quick Install

### Option 1: OpenCode Skill Add

```bash
opencode skill add github.com/manthan89/session-merge
```

### Option 2: Manual Clone

```bash
git clone https://github.com/manthan89/session-merge ~/.agents/skills/session-merge
```

### Option 3: Direct Download

```bash
mkdir -p ~/.agents/skills/session-merge
curl -L https://github.com/manthan89/session-merge/archive/main.tar.gz | tar -xz -C ~/.agents/skills/session-merge --strip-components=1
```

## Configuration

Add these environment variables to `~/.bashrc` or `~/.profile`:

```bash
# Required: None (all have sensible defaults)

# Optional: Customize behavior
export SESSION_MERGE_SHORT_THRESHOLD=10      # Messages below = "short"
export SESSION_MERGE_AGGRESSIVENESS="balanced"  # conservative | balanced | aggressive
export SESSION_MERGE_TITLE_THRESHOLD=0.6     # Title similarity cutoff (0.0-1.0)
export SESSION_MERGE_TIME_WINDOW=24          # Hours for time proximity
export SESSION_MERGE_AUTO_CONFIRM="false"    # Skip confirmation prompts
export SESSION_MERGE_DB_PATH=""              # Custom database path (auto-detect by default)
```

## Verify Installation

```bash
# Test discovery
python3 ~/.agents/skills/session-merge/scripts/find_candidates.py --help

# Test merge engine
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py --help

# Run tests
python3 -m unittest discover -s ~/.agents/skills/session-merge/tests -v
```

## Directory Structure

After installation, these directories are created automatically:

```
~/.local/share/session-merge/
├── backups/          # Database backups (created before each merge)
├── archives/         # Markdown exports of merged sessions
└── merge-history.log # Audit log of all merge operations
```

## First Run

1. Run discovery to see what sessions can be merged:
   ```bash
   python3 ~/.agents/skills/session-merge/scripts/find_candidates.py
   ```

2. Review the output — clusters are grouped by topic with auto-merge recommendations.

3. Execute merges (dry run first):
   ```bash
   python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py --dry-run
   ```

4. If satisfied, run without `--dry-run`.
