# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-01-29

### Added

- Project structure with Poetry package management
- CLI framework using Click with commands: status, balance, positions, rules, start, stop
- Configuration system with environment support (paper/prod)
- Logging infrastructure with file and console output
- Trade audit log capability
- Environment-based configuration (.env.paper, .env.prod)
- Safety controls: production disabled by default, confirmation flags required
- Rich terminal output with formatted tables
- Test suite with pytest

### Dependencies

- click, requests, pandas, python-dotenv, pyyaml, alpaca-py, rich
- Dev: pytest, pytest-cov, ruff, mypy

## [0.0.1] - 2026-01-30

### Added

- Initial Setup
