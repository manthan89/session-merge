# Session Merge

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│   🔍  Find duplicate sessions                            │
│   🔄  Merge with UUID remapping                          │
│   🛡️  Soft-delete only, full undo                        │
│   📝  Every merge documented                             │
│                                                          │
│   Session Merge — Clean up your AI coding history        │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-30%2F30%20passing-brightgreen.svg)](tests/)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](CHANGELOG.md)

---

## 🎯 Why This Exists

Your AI coding tool creates a session for every conversation. After a week, you have 50+ sessions — duplicates, forks, abandoned attempts. Finding the right conversation becomes a chore.

**Session Merge** finds related sessions, consolidates them safely, and gives you your sanity back.

### Before

```
📁 Your Sessions (50+)
├── Telegram bot (481 msgs)
├── Fix telegram bot (5 msgs)
├── Fixing telegram bot (5 msgs)
├── Stop Auto-Start Loop (8 msgs)
├── Telegram bot callback fix (12 msgs)
├── Content Pipeline Setup (45 msgs)
├── Content Pipeline Fixes (32 msgs)
├── Content Pipeline Architecture (28 msgs)
├── ... and 42 more
```

### After

```
📁 Your Sessions (12)
├── Telegram bot (511 msgs) ← merged 4 sessions
├── Content Pipeline (105 msgs) ← merged 3 sessions
├── ... and 10 more clean sessions
```

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Auto-detection** | Finds related sessions by title similarity, time proximity, and content overlap |
| 🔒 **UUID remapping** | Every message and part gets a new ID — never reuses existing IDs |
| 🗂️ **Soft-delete only** | Sessions are archived (`time_archived`), never hard-deleted |
| 🔄 **Full undo** | Every merge is reversible via automatic backup restoration |
| 📝 **Merge summary** | Injects a SYSTEM message documenting exactly what was merged |
| 🔗 **Share URL transfer** | Preserves share links by transferring them to the target session |
| 📦 **Markdown export** | Archive sessions as human-readable files before merging |
| 🧠 **Memory integration** | Updates OpenCode memory system files automatically |
| ⚡ **Pre-filtered clustering** | O(N) pre-filter by project + time window before expensive similarity matching |

---

## 🚀 Quick Start

```bash
# 1. Install
git clone https://github.com/manthan89/session-merge ~/.agents/skills/session-merge

# 2. Discover merge candidates
python3 ~/.agents/skills/session-merge/scripts/find_candidates.py

# 3. Merge (dry run first)
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py --dry-run
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface                          │
│  (Natural Language / CLI / Auto-Scan)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   Skill Orchestrator                        │
│  find_candidates.py → cluster_sessions()                    │
│  merge_sessions.py → execute_merge()                        │
│  export_session.py → export_to_markdown()                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Safety Layer                               │
│  1. Create backup                                           │
│  2. BEGIN TRANSACTION                                       │
│  3. Pre-merge checks                                        │
│  4. Copy messages with NEW UUIDs                            │
│  5. Copy parts with NEW UUIDs (remapped message_id)         │
│  6. Insert separator messages                               │
│  7. Insert merge summary                                    │
│  8. Transfer share URLs                                     │
│  9. Soft-delete source sessions                             │
│  10. Post-merge verification                                │
│  11. COMMIT or ROLLBACK                                     │
│  12. Update memory system                                   │
│  13. Log merge action                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   SQLite Database                           │
│  session → message → part → todo → session_share            │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Merge Rules

| Source → Target | Short (<10 msgs) | Long (≥10 msgs) |
|-----------------|-----------------|-----------------|
| **Short** | ✅ Auto-merge into earliest | ✅ Auto-merge into long |
| **Long** | (N/A) | ⚠️ Requires confirmation |

---

## 🛡️ Safety Guarantees

```
Backup First → Transaction-Safe → Verify → Commit → Log
     │               │              │         │        │
     ▼               ▼              ▼         ▼        ▼
  Timestamped     All-or-       Post-merge  Only on   Audit
  .db backup      nothing       checks pass success   trail
```

### What This Means

- **NEVER** modifies your database without a backup first
- **ALWAYS** uses SQLite transactions — either everything succeeds or nothing changes
- **NEVER** reuses message or part IDs — always generates new UUIDs
- **NEVER** hard-deletes sessions — soft-delete only via `time_archived`
- **ALWAYS** injects a merge summary message into the target session
- **ALL** operations are reversible via `--undo` flag

---

## 🔧 Configuration

All configuration is via environment variables. Add these to `~/.bashrc`:

```bash
# Matching behavior
export SESSION_MERGE_SHORT_THRESHOLD=10       # Messages below = "short"
export SESSION_MERGE_TITLE_THRESHOLD=0.6      # Title similarity cutoff (0.0-1.0)
export SESSION_MERGE_TIME_WINDOW=24           # Hours for time proximity
export SESSION_MERGE_AGGRESSIVENESS="balanced" # conservative | balanced | aggressive

# Automation
export SESSION_MERGE_AUTO_CONFIRM="false"     # Skip confirmation prompts
export SESSION_MERGE_DB_PATH=""               # Custom database path (auto-detect)
```

<details>
<summary><strong>Full configuration reference</strong></summary>

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_MERGE_SHORT_THRESHOLD` | `10` | Messages below this count are considered "short" |
| `SESSION_MERGE_TITLE_THRESHOLD` | `0.6` | Minimum title similarity score (0.0-1.0) to cluster |
| `SESSION_MERGE_TIME_WINDOW` | `24` | Hours within which sessions are considered temporally related |
| `SESSION_MERGE_AGGRESSIVENESS` | `balanced` | Matching strictness: `conservative`, `balanced`, or `aggressive` |
| `SESSION_MERGE_AUTO_CONFIRM` | `false` | Skip interactive confirmation prompts |
| `SESSION_MERGE_DB_PATH` | `""` | Custom database path (auto-detects OpenCode by default) |
| `SESSION_MERGE_TRIGGER` | `manual` | How the skill activates: `manual`, `command`, or `auto-scan` |

</details>

---

## 📋 Test Results

| Category | Tests | Status |
|----------|-------|--------|
| Fuzzy Matching | 6 | ✅ |
| Keyword Overlap | 3 | ✅ |
| Health Scoring | 2 | ✅ |
| Clustering | 3 | ✅ |
| Fork Detection | 1 | ✅ |
| Merge Type Classification | 3 | ✅ |
| UUID Remapping | 3 | ✅ |
| Message Ordering | 2 | ✅ |
| Soft-Delete | 2 | ✅ |
| Share URL Transfer | 1 | ✅ |
| Backup Creation | 1 | ✅ |
| Rollback on Failure | 1 | ✅ |
| Database Integrity | 1 | ✅ |
| Undo/Restore | 1 | ✅ |
| **Total** | **30** | **✅ 100%** |

Run tests yourself:
```bash
python3 -m unittest discover -s tests -v
```

---

## 📁 Project Structure

```
session-merge/
├── SKILL.md                    # OpenCode skill entry point
├── README.md                   # This file
├── LICENSE                     # MIT License
├── CHANGELOG.md                # Version history
├── CONTRIBUTING.md             # How to contribute
├── SECURITY.md                 # Security policy
├── .gitignore
├── scripts/
│   ├── find_candidates.py      # Discovery, clustering, health scoring
│   ├── merge_sessions.py       # Core merge with UUID remapping + safety
│   └── export_session.py       # Export session to markdown archive
├── rules/
│   ├── install.md              # Setup guide + env var config
│   └── safety.md               # Safety guarantees, undo procedures
└── tests/
    ├── test_clustering.py      # Clustering engine tests
    └── test_merge_engine.py    # Merge engine tests
```

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

### Quick Start for Contributors

```bash
# Fork and clone
git clone https://github.com/manthan89/session-merge.git
cd session-merge

# Create a branch
git checkout -b feature/my-feature

# Run tests
python3 -m unittest discover -s tests -v

# Commit and push
git commit -m "feat: add my feature"
git push origin feature/my-feature
```

---

## 🪙 Send Me Some Tokens

I don't drink tea. I run on tokens. Send me some and I'll merge your sessions faster.

| Token | Address |
|-------|---------|
| **BTC** | `bc1qw92r7nfjsannj83vtztx3fzcrwexgg79xmjn0l` |
| **ETH** | `0xCC9A314112aedc493e0ff8597f665E5fBa0d2f10` |

No pressure. The tool is free. The tokens are for my ego. 🪙

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

**Copyright (c) 2026 Manthan Patel**
