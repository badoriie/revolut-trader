# Revolut Trader - Development Commands
# ==========================================
# This justfile contains ONLY development commands.
# For functional commands (run, backtest, ops, db, etc.), use the revt CLI.
#
# Quick Start:
#   just install       install dependencies
#   just test          run tests with coverage
#   just check         run all quality checks
#   just env           show current environment
#
# See: just --list

# Default recipe (show help)
default:
    @just --list

# ============================================================================
# Setup & Installation
# ============================================================================

# Install/update dependencies with uv
install:
    @echo "Installing dependencies with uv..."
    @uv sync --extra dev --extra analytics
    @echo "Installing pre-commit hooks..."
    @uv run pre-commit install
    @uv run pre-commit install --hook-type commit-msg
    @echo "Done. Pre-commit hooks installed (pre-commit + commit-msg)"

# Remove cache files and artifacts
clean:
    @find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    @find . -type f -name "*.pyc" -delete 2>/dev/null || true
    @find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    @find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    @find . -type d -name ".pyright" -exec rm -rf {} + 2>/dev/null || true
    @find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    @find . -type f -name ".coverage" -delete 2>/dev/null || true
    @find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
    @echo "Clean complete"

# Remove ALL generated files (data, backups, venv) - requires confirmation
deep-clean:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "WARNING: This will delete ALL generated files including database, backups, and venv."
    read -p "Type 'YES' to confirm: " confirm
    if [ "$confirm" != "YES" ]; then
        echo "Cancelled"
        exit 1
    fi
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pyright" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name ".coverage" -delete 2>/dev/null || true
    find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
    rm -rf data results backups .venv .uv 2>/dev/null || true
    echo "Deep clean complete. Run 'just install' to reinstall dependencies."

# ============================================================================
# Code Quality
# ============================================================================

# Run pre-commit hooks on all files
pre-commit:
    @uv run pre-commit run --all-files

# Run tests with coverage
test:
    @uv run pytest --cov=src --cov-report=term-missing --cov-report=html
    @echo "Coverage report: htmlcov/index.html"

# Check code with ruff
lint:
    @uv run ruff check src/ tests/ cli/

# Format code with ruff
format:
    @uv run ruff format src/ tests/ cli/
    @uv run ruff check --fix src/ tests/ cli/

# Run pyright type checking
typecheck:
    @uv run pyright src/ cli/

# Run bandit static security analysis
security:
    @uv run bandit -c pyproject.toml -r src/ cli/

# Run all quality checks (lint, format, typecheck, security, test)
check: lint format typecheck security test
    @echo "All quality checks passed"

# ============================================================================
# Development Utilities
# ============================================================================

# Show current environment (dev/int/prod)
env:
    @uv run python -c "from cli.utils.env_detect import detect_env; env = detect_env(); print(f'Current environment: {env}')"

# Sync CLAUDE.md to .github/copilot-instructions.md
sync-copilot:
    @cp CLAUDE.md .github/copilot-instructions.md
    @echo "Synced CLAUDE.md → .github/copilot-instructions.md"

# Sync agent configurations from .claude/agents/ to .github/agents/
sync-agents:
    @echo "Syncing agents from .claude/agents/ → .github/agents/..."
    @cp .claude/agents/audit-docs.md .github/agents/audit-docs.agent.md
    @cp .claude/agents/backtest-analyst.md .github/agents/backtest-analyst.agent.md
    @cp .claude/agents/code-improvement.md .github/agents/code-improvement.agent.md
    @cp .claude/agents/security-reviewer.md .github/agents/security-reviewer.agent.md
    @cp .claude/agents/strategy-review.md .github/agents/strategy-review.agent.md
    @cp .claude/agents/testing-debug.md .github/agents/testing-debug.agent.md
    @echo "✅ All agents synced successfully"

# Sync both CLAUDE.md and agents
sync-all: sync-copilot sync-agents
    @echo "✅ All documentation and agents synced"

# Generate class diagrams using pyreverse
diagrams:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p docs/diagrams
    echo "Generating class diagrams..."
    uv run pyreverse -o dot -p revolut-trader src/
    mv classes_revolut-trader.dot docs/diagrams/ 2>/dev/null || true
    mv packages_revolut-trader.dot docs/diagrams/ 2>/dev/null || true
    echo "✓ Diagrams generated in docs/diagrams/ (DOT format)"
    echo ""
    if command -v dot >/dev/null 2>&1; then
        echo "Converting to PNG..."
        dot -Tpng docs/diagrams/classes_revolut-trader.dot -o docs/diagrams/classes_revolut-trader.png 2>/dev/null || true
        dot -Tpng docs/diagrams/packages_revolut-trader.dot -o docs/diagrams/packages_revolut-trader.png 2>/dev/null || true
        echo "✓ PNG diagrams generated"
    else
        echo "Note: Graphviz not installed - DOT files generated only"
        echo "Install Graphviz to convert to PNG: brew install graphviz"
        echo "Or view DOT files online: https://dreampuf.github.io/GraphvizOnline/"
    fi
