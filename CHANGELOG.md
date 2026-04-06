# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-06

### Added
- Session discovery engine with title similarity, time proximity, and content overlap clustering
- Merge engine with UUID remapping for all messages and parts
- Soft-delete only (sessions archived via `time_archived`, never hard-deleted)
- SQLite transaction safety with automatic rollback on failure
- Merge summary injection as SYSTEM message in target session
- Share URL transfer from source to target sessions
- Markdown export for session archival
- Memory system integration (updates OpenCode memory files)
- Pre-filtered clustering (O(N) by project + time window before expensive similarity)
- Undo/restore from automatic backup
- Comprehensive test suite (30 tests, 100% passing)
- CLI interface: `--dry-run`, `--undo`, `--target`, `--sources`, `--force`
- Environment variable configuration system

### Safety Features
- Backup-first: every merge creates timestamped database backup
- Transaction-safe: all-or-nothing via SQLite transactions
- UUID remapping: never reuses existing message/part IDs
- Post-merge verification: confirms success before committing
- Rollback on ANY failure: no partial merges possible
