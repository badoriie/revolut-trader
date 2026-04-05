---
name: code-improvement
description: Code quality and modernization review. Checks dependencies, reviews patterns, identifies security issues, produces a prioritized improvement backlog. Use for periodic quality reviews or before releases.
tools: Read Glob Grep Bash WebFetch WebSearch
---

Perform a comprehensive code quality and modernization review. Identify opportunities for improvement across dependencies, tooling, testing, performance, and code quality.

## 1. Dependency Updates

- Read `pyproject.toml` to get current versions
- Check PyPI for the latest versions of: `httpx`, `pydantic`, `sqlalchemy`, `pytest`, `ruff`, `pyright`, `loguru`, `cryptography`, `matplotlib`, `fpdf2`
- Check for security vulnerabilities in current versions
- Suggest version updates with rationale (new features, performance, security)

## 2. Python Version & Features

- Check `requires-python` in `pyproject.toml`
- Identify newer Python features that could improve code (`X | Y` unions, pattern matching, new stdlib)
- Check for deprecated features in use

## 3. Code Quality & Patterns

- **Type hints**: Any `Any`, missing return types?
- **Error handling**: Bare `except:`? Exceptions swallowed silently?
- **Constants**: Magic numbers/strings that should be extracted?
- **Complexity**: Functions with cognitive complexity > 15?
- **Documentation**: Docstrings missing or inaccurate?

## 4. Testing Improvements

- Run `just test` — confirm coverage ≥ 97%
- Identify untested edge cases and error conditions
- Check for weak tests: missing assertions, overly broad except blocks

## 5. CI/CD & Automation

- Check `.github/workflows/*.yml` for outdated action versions
- Identify missing checks (dependency scanning, SBOM)
- Security best practices in workflows

## 6. Performance Opportunities

- Database: N+1 queries, missing indices
- Async: blocking calls in async functions
- Caching: repeated expensive operations

## 7. Security & Safety

- Any hardcoded secrets or credentials?
- All monetary values using `Decimal`, not `float`?
- Error messages leaking sensitive information?

## 8. Summary Report

Produce a prioritized backlog:

```
# Code Improvement Report

## Executive Summary
- X critical issues
- Y high-priority improvements
- Z outdated dependencies

## Top 5 Recommendations

## Quick Wins (low effort, high impact)

## Dependency Updates
| Package | Current | Latest | Notes |
```
