# Safety Procedures

## Core Safety Principles

1. **Backup-first**: Every merge creates a timestamped database backup before any changes
2. **Transaction-safe**: All operations wrapped in SQLite transactions (all-or-nothing)
3. **UUID remapping**: Never reuse message or part IDs — always generate new UUIDs
4. **Soft-delete only**: Sessions are archived (time_archived set), never hard-deleted
5. **Merge summary**: Every merge injects a SYSTEM message documenting what was merged
6. **Verification**: Post-merge checks confirm success before committing
7. **Reversible**: Every merge can be undone via backup restoration

## Safety Flow

```
1. Create backup → fail? ABORT
2. BEGIN TRANSACTION
3. Copy messages with NEW UUIDs
4. Copy parts with NEW UUIDs (remapped message_id)
5. Insert separator messages
6. Insert merge summary
7. Transfer share URLs
8. Soft-delete source sessions
9. Verify merge summary exists → fail? ROLLBACK
10. Verify sources archived → fail? ROLLBACK
11. Verify database integrity → fail? ROLLBACK
12. COMMIT
13. Update memory system
14. Log merge action
```

## Undo a Merge

```bash
# Undo last merge (uses latest backup)
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py --undo

# Undo with specific backup
python3 ~/.agents/skills/session-merge/scripts/merge_sessions.py --undo --backup /path/to/backup
```

## Backup Locations

All backups are stored in:
```
~/.local/share/session-merge/backups/opencode.db.backup.YYYYMMDD_HHMMSS
```

## Merge Log

All merge operations are logged to:
```
~/.local/share/session-merge/merge-history.log
```

Each entry includes:
- Timestamp
- Target session ID
- Source session IDs
- Backup path
- Total messages merged

## What Could Go Wrong

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Backup creation fails | Pre-merge check | Abort, notify user |
| Merge summary not written | Post-merge verification | Rollback, restore backup |
| Database integrity fails | Post-merge check | Restore from backup |
| Share URL transfer fails | Verification step | Abort, notify user |
| Partial merge (some sources merged, some not) | Transaction rollback | All-or-nothing, no partial state |

## Manual Recovery

If something goes wrong and undo doesn't work:

```bash
# Manual restore from backup
cp ~/.local/share/session-merge/backups/opencode.db.backup.YYYYMMDD_HHMMSS ~/.local/share/opencode/opencode.db

# Verify integrity
sqlite3 ~/.local/share/opencode/opencode.db "PRAGMA integrity_check;"
```
