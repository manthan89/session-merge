# Contributing to Session Merge

Thank you for your interest in contributing! This guide will help you get started.

## 🚀 Quick Start

```bash
# Fork and clone
git clone https://github.com/manthan89/session-merge.git
cd session-merge

# Create a virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate

# Run tests to verify setup
python3 -m unittest discover -s tests -v
```

## 📋 How to Contribute

### Reporting Bugs

1. Check the [Issues](https://github.com/manthan89/session-merge/issues) to see if it's already reported
2. If not, open a new issue using the bug report template
3. Include:
   - Python version and OS
   - Steps to reproduce
   - Expected vs actual behavior
   - Any relevant logs or error messages

### Suggesting Features

1. Check the [Issues](https://github.com/manthan89/session-merge/issues) to see if it's already suggested
2. If not, open a new issue using the feature request template
3. Describe the problem, proposed solution, and alternatives considered

### Submitting Pull Requests

1. Create a branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Run tests: `python3 -m unittest discover -s tests -v`
4. Commit with a clear message: `git commit -m "feat: add my feature"`
5. Push: `git push origin feature/my-feature`
6. Open a Pull Request

## 🧪 Testing

All contributions must include tests:

```bash
# Run all tests
python3 -m unittest discover -s tests -v

# Run specific test file
python3 -m unittest tests.test_merge_engine -v

# Run specific test
python3 -m unittest tests.test_merge_engine.TestUUIDRemapping -v
```

### Writing Tests

- Add tests for any new functionality
- Use the existing test patterns in `tests/`
- Tests should be self-contained (create their own test databases)
- Clean up temporary files in `tearDown()`

## 📝 Code Style

- Follow [PEP 8](https://pep8.org/) for Python code
- Use double quotes for strings
- Use type hints where practical
- Write docstrings for all public functions
- Keep functions focused and under 50 lines when possible

## 🔒 Security

- Never commit database files, backups, or archives
- Never hardcode paths — use config or environment variables
- Never log sensitive data (session content, user messages)
- See [SECURITY.md](SECURITY.md) for reporting security issues

## 📂 Project Structure

```
session-merge/
├── scripts/          # Core Python scripts
├── tests/            # Test suite
├── rules/            # Skill rules and documentation
├── SKILL.md          # OpenCode skill entry point
├── README.md         # Main documentation
├── CHANGELOG.md      # Version history
├── CONTRIBUTING.md   # This file
└── SECURITY.md       # Security policy
```

## 🤝 Code of Conduct

- Be respectful and inclusive
- Focus on the problem, not the person
- Accept constructive feedback gracefully
- Help others learn and grow

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.
