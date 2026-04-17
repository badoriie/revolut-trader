# Git Commit Instructions

This project uses [Conventional Commits](https://www.conventionalcommits.org/) enforced via [Commitizen](https://commitizen-tools.github.io/commitizen/).

## Format

```
<type>[optional scope]: <description>

[optional body]

[optional footer]
```

## Types

| Type | When to use | SemVer impact |
|------|-------------|---------------|
| `feat` | Introduces a new feature | MINOR |
| `fix` | Patches a bug | PATCH |
| `docs` | Documentation changes only | none |
| `refactor` | Code change that neither fixes a bug nor adds a feature | none |
| `test` | Adding or updating tests | none |
| `chore` | Maintenance tasks (deps, tooling, config) | none |
| `perf` | Performance improvement | none |
| `ci` | CI/CD pipeline changes | none |
| `style` | Formatting, whitespace — no logic change | none |

## Breaking Changes

Append `!` to the type, or add a `BREAKING CHANGE:` footer:

```
feat!: remove deprecated endpoint

BREAKING CHANGE: /v1/orders endpoint removed; use /v2/orders instead.
```

## Examples

```
feat(executor): add LIMIT close with MARKET fallback for take-profit exits

fix(risk): prevent negative position size on partial fill

docs: update END_USER_GUIDE with limit close configuration

refactor(config): extract _load_strategy_bool helper

test(executor): add polling and timeout coverage for adaptive close

chore: bump commitizen to 4.x
```

## Helper

Use Commitizen's interactive prompt instead of writing the message manually:

```bash
uv run cz commit
```

Commitizen validates the message format and bumps the version automatically on `cz bump`.

## Rules

- **Subject line**: imperative mood, lowercase, no trailing period, ≤72 characters.
- **Scope**: optional, lowercase, describes the module/area (e.g. `executor`, `config`, `risk`).
- **Body**: wrap at 100 characters; explain *why*, not *what*.
- **Footer**: reference issues (`Closes #123`) or document breaking changes.
