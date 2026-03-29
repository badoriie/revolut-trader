# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the revt standalone binary.

Run from the project root:
    uv run pyinstaller build/revt.spec --distpath dist --workpath build/.pyinstaller

The resulting binary at dist/revt is fully self-contained — no Python, no uv,
no virtual environment needed.  Only the external `op` CLI (1Password) must be
on the system PATH for credential commands.

Release platforms (built by CI):
    revt-macos-arm64   macOS Apple Silicon (M1/M2/M3/M4)
    revt-linux-arm64   Linux ARM64 (Raspberry Pi 4+, AWS Graviton)
"""

from pathlib import Path

# Project root is one level above this spec file
PROJECT_ROOT = Path(SPECPATH).parent  # noqa: F821 — SPECPATH set by PyInstaller

a = Analysis(
    [str(PROJECT_ROOT / "cli" / "revt.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # ── CLI modules (all lazily imported inside cmd_* functions) ──────────
        "cli.run",
        "cli.backtest",
        "cli.backtest_compare",
        "cli.api_test",
        "cli.db_manage",
        "cli.analytics_report",
        # ── src modules ──────────────────────────────────────────────────────
        "src.bot",
        "src.config",
        "src.api",
        "src.api.client",
        "src.api.mock_client",
        "src.backtest.engine",
        "src.execution.executor",
        "src.risk_management.risk_manager",
        "src.strategies.base_strategy",
        "src.strategies.market_making",
        "src.strategies.momentum",
        "src.strategies.mean_reversion",
        "src.strategies.multi_strategy",
        "src.strategies.breakout",
        "src.strategies.range_reversion",
        "src.models.domain",
        "src.models.db",
        "src.utils.db_persistence",
        "src.utils.db_encryption",
        "src.utils.onepassword",
        "src.utils.rate_limiter",
        "src.utils.fees",
        "src.utils.indicators",
        # ── third-party ───────────────────────────────────────────────────────
        "loguru",
        "loguru._defaults",
        "sqlalchemy",
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.sql.default_comparator",
        "sqlalchemy.orm",
        "pydantic",
        "pydantic.v1",
        "pydantic_settings",
        "cryptography",
        "cryptography.fernet",
        "cryptography.hazmat.backends",
        "cryptography.hazmat.backends.openssl",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.primitives.serialization",
        "httpx",
        "httpx._transports.default",
        "anyio",
        "anyio._backends._asyncio",
        "h11",
        "certifi",
        "sniffio",
    ],
    # Exclude heavy optional deps — analytics charts are not needed in the binary
    excludes=["matplotlib", "numpy", "pytest", "ruff", "pyright", "bandit"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)  # noqa: F821 — PYZ set by PyInstaller

exe = EXE(  # noqa: F821 — EXE set by PyInstaller
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="revt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,         # UPX compression can trigger AV false-positives on some systems
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # CLI tool — terminal output required
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # None = native arch of the build machine
    codesign_identity=None,
    entitlements_file=None,
)
