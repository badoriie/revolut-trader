Perform a comprehensive code quality and modernization review. Identify opportunities for improvement across dependencies, tooling, testing, performance, and code quality.

## 1. Dependency Updates

Check for outdated dependencies and new features:

- Read `pyproject.toml` to get current versions
- Check PyPI for the latest versions of key dependencies:
  - `httpx` - async HTTP client
  - `pydantic` - data validation
  - `sqlalchemy` - database ORM
  - `pytest` - testing framework
  - `ruff` - linter/formatter
  - `pyright` - type checker
  - `loguru` - logging
  - `cryptography` - encryption (Fernet)
  - `matplotlib` - plotting (optional)
  - `fpdf2` - PDF generation (optional)
- Review dependency groups (`dev`, `analytics`) - are they still appropriate?
- Check for security vulnerabilities in current versions
- Suggest version updates with rationale (new features, performance, security)
- Verify compatibility between dependencies

## 2. Python Version & Features

Review Python language version:

- Check `pyproject.toml` for `requires-python` version
- Identify if newer Python features could improve code:
  - Type hints improvements (e.g., `X | Y` instead of `Union[X, Y]`)
  - Pattern matching (`match`/`case`)
  - New standard library features
  - Performance improvements in newer versions
- Check if any deprecated features are being used

## 3. Code Quality & Patterns

Scan the codebase for improvement opportunities:

- **Type hints**: Are all functions fully typed? Check for `Any`, missing return types
- **Error handling**: Are exceptions handled appropriately? Any bare `except:`?
- **Constants**: Are magic numbers/strings extracted to constants?
- **Code duplication**: Any repeated code blocks that could be extracted?
- **Design patterns**: Could any patterns improve clarity (factory, strategy, etc.)?
- **Complexity**: Are there any overly complex functions (high cyclomatic complexity)?
- **Documentation**: Are docstrings complete and accurate?
- **Naming**: Are variable/function names clear and consistent?

## 4. Testing Improvements

Review test coverage and quality:

- Run `make test` to get current coverage (target: ≥97%)
- Identify untested or under-tested code paths:
  - Edge cases
  - Error conditions
  - Integration points
- Check for test quality issues:
  - Tests that don't actually assert anything
  - Overly broad `try`/`except` in tests
  - Missing parametrize opportunities
  - Slow tests that could be optimized
- Suggest new test categories:
  - Property-based testing (hypothesis)?
  - Performance/benchmark tests?
  - Mutation testing to verify test quality?

## 5. CI/CD & Automation

Review GitHub Actions workflows:

- Check `.github/workflows/*.yml` for:
  - Outdated action versions (e.g., `actions/checkout@v3` → `@v4`)
  - Missing useful checks (dependency scanning, SBOM generation, etc.)
  - Optimization opportunities (caching, matrix builds)
  - Security best practices
- Check for missing automations:
  - Automated dependency updates (Dependabot/Renovate)?
  - Automated release notes?
  - Performance regression detection?

## 6. Performance Opportunities

Identify potential performance improvements:

- **Database queries**: Any N+1 queries? Missing indices?
- **Async operations**: Could any sync code be made async?
- **Caching**: Are there repeated expensive operations?
- **Data structures**: Are the right data structures being used?
- **Algorithms**: Any O(n²) that could be O(n log n) or O(n)?
- **Memory usage**: Any unnecessary copies or large data retention?

## 7. Security & Safety

Review security practices:

- **Secrets management**: Is 1Password integration secure? Any hardcoded secrets?
- **Input validation**: Are all user inputs validated?
- **SQL injection**: Are parameterized queries used everywhere?
- **Encryption**: Is encryption used correctly? Key rotation?
- **Dependencies**: Any known CVEs in dependencies?
- **API security**: Are API keys stored securely? Rate limiting?
- **Error messages**: Do they leak sensitive information?

## 8. Tooling & Developer Experience

Evaluate developer tooling:

- **Pre-commit hooks**: Are they comprehensive? Too slow?
- **Makefile**: Are targets well-organized? Any missing useful targets?
- **Documentation**: Is setup clear? Are troubleshooting guides adequate?
- **Debugging**: Are there debug utilities? Logging sufficient?
- **VSCode/IDE**: Is `.vscode/settings.json` present with recommended settings?
- **Development database**: Easy to reset/seed for testing?

## 9. Modern Python Ecosystem Tools

Check for beneficial new tools:

- **uv**: Already using it — check for new features
- **ruff**: Already using it — check if it can replace more tools
- **Monitoring**: Should we add runtime monitoring (e.g., Sentry)?
- **Profiling**: Should we add profiling tools (py-spy, memray)?
- **Documentation**: Should we use mkdocs/sphinx for API docs?
- **Type checking**: Are we using pyright optimally? Need `--strict`?
- **Benchmarking**: Should we track performance over time (asv, pytest-benchmark)?

## 10. Architecture & Design

Review high-level architecture:

- **Separation of concerns**: Are responsibilities well-separated?
- **Dependency injection**: Could it improve testability?
- **Configuration**: Is config management clean? Environment parity?
- **Error handling**: Is there a consistent error handling strategy?
- **Logging**: Is logging structured and consistent?
- **Modularity**: Are components loosely coupled?
- **Scalability**: Are there scalability bottlenecks?

## 11. Documentation Updates Needed

Identify documentation that needs updating:

- Are all new features documented in `README.md`?
- Does `CLAUDE.md` reflect current architecture?
- Are `docs/*.md` files up to date?
- Do docstrings match implementation?
- Are code examples in docs still valid?

## 12. Package Management & Build

Review package configuration:

- **pyproject.toml**: Is metadata complete? Entry points correct?
- **Build system**: Is the build reproducible?
- **Lock file**: Is `uv.lock` committed? Does it need updating?
- **Optional dependencies**: Are they well-organized?
- **Scripts/CLI**: Are entry points working correctly?

## 13. Backlog & Technical Debt

Create a prioritized improvement backlog:

1. **Critical** (security, correctness)
1. **High** (significant quality/performance improvements)
1. **Medium** (nice-to-have modernizations)
1. **Low** (cosmetic improvements)

For each item provide:

- **What**: Clear description of the improvement
- **Why**: Rationale and benefit
- **How**: Implementation approach
- **Effort**: Estimated complexity (small/medium/large)
- **Impact**: Expected benefit (low/medium/high)

## 14. Summary Report

Provide a structured summary:

```markdown
# Code Improvement Report

## Executive Summary
- X critical issues found
- Y high-priority improvements identified
- Z outdated dependencies
- Overall code quality: [score/10]

## Top 5 Recommendations
1. [Most impactful improvement]
2. [Second most impactful]
...

## Quick Wins
[Low-effort, high-impact improvements that should be done first]

## Long-term Improvements
[Strategic improvements requiring more effort]

## Dependency Updates
| Package | Current | Latest | Notes |
|---------|---------|--------|-------|
| ...     | ...     | ...    | ...   |
```

## Guidelines

- Be specific: "Update httpx from 0.27.0 to 0.28.0 for HTTP/2 support" not "update dependencies"
- Provide context: Explain WHY each improvement matters
- Consider tradeoffs: Mention any downsides or risks
- Prioritize ruthlessly: Focus on high-impact improvements
- Be actionable: Each suggestion should be implementable
- Check compatibility: Don't suggest breaking changes without mitigation
- Respect project style: Suggestions should fit the project's philosophy
- Verify suggestions: Test any code examples you provide
