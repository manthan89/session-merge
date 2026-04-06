# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | ✅        |

## Reporting a Vulnerability

We take the security of Session Merge seriously. This tool operates directly on your session database, so any vulnerability could result in data loss or corruption.

### How to Report

**Do NOT open a public issue** for security vulnerabilities.

Instead, report vulnerabilities by:

1. Opening a private issue at: https://github.com/manthan89/session-merge/security/advisories
2. Or emailing: trivedi.manthan89@gmail.com with subject "Session Merge Security Report"

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if known)

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix deployed:** Within 2 weeks (depending on severity)
- **Public disclosure:** After fix is released and users have had time to update

### What We Consider Security Issues

- Database corruption during merge operations
- Data loss from failed merges
- Unauthorized access to session data
- SQL injection vulnerabilities
- Race conditions in concurrent operations
- Backup integrity failures

### What We Don't Consider Security Issues

- Session clustering false positives (this is a feature quality issue)
- Performance degradation with large databases
- Compatibility issues with specific OpenCode versions
