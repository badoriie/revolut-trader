#!/usr/bin/env python3
"""View encrypted logs from the database.

Shows WARNING/ERROR/CRITICAL logs that were automatically saved during bot operation.

Usage:
    uv run python cli/view_logs.py [--level LEVEL] [--limit N] [--follow] [--session ID]

Examples:
    uv run python cli/view_logs.py                    # Last 50 logs
    uv run python cli/view_logs.py --level ERROR      # Only errors
    uv run python cli/view_logs.py --limit 100        # Last 100 logs
    uv run python cli/view_logs.py --follow           # Tail mode (like tail -f)
    uv run python cli/view_logs.py --session 42       # Logs from session 42
"""

import argparse
import time
from datetime import datetime

from loguru import logger

from src.utils.db_persistence import DatabasePersistence

# Suppress decryption warnings when viewing logs - they're expected for old test data
logger.disable("src.utils.db_encryption")


def format_log_entry(log: dict) -> str:
    """Format a log entry for display.

    Args:
        log: Log entry dict with timestamp, level, module, message, session_id.

    Returns:
        Formatted string for terminal output.
    """
    # Parse timestamp
    ts = log["timestamp"]
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        time_str = str(ts)

    # Color codes for different log levels
    colors = {
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[95m",  # Magenta
    }
    reset = "\033[0m"

    level = log["level"]
    color = colors.get(level, "")
    module = log.get("module", "unknown")
    message = log.get("message", "")
    session_id = log.get("session_id", "")

    # Format: 2026-04-01 13:20:15 [ERROR] src.bot: Connection failed (session: 42)
    session_part = f" (session: {session_id})" if session_id else ""
    return f"{time_str} {color}[{level:8s}]{reset} {module}: {message}{session_part}"


def view_logs(
    persistence: DatabasePersistence,
    level: str | None = None,
    limit: int = 50,
    session_id: int | None = None,
) -> None:
    """Display logs from the database.

    Args:
        persistence: Database persistence instance.
        level: Optional level filter (WARNING, ERROR, CRITICAL).
        limit: Maximum number of logs to display.
        session_id: Optional session ID filter.
    """
    # When filtering by session, load more logs to account for old encrypted data
    # that will be skipped during decryption
    load_limit = limit * 20 if session_id is not None else limit
    logs = persistence.load_log_entries(since=None, level=level, limit=load_limit)

    # Filter by session if requested and handle decryption errors
    filtered_logs = []
    for log in logs:
        # Skip logs with empty or encrypted messages (decryption failed)
        msg = log.get("message")
        if not msg or (isinstance(msg, str) and msg.startswith("gAAAAA")):
            continue

        # Apply session filter
        if session_id is not None and log.get("session_id") != session_id:
            continue

        filtered_logs.append(log)

        # Stop when we have enough logs
        if len(filtered_logs) >= limit:
            break

    if not filtered_logs:
        print("No logs found.")
        return

    print(f"\nShowing {len(filtered_logs)} log entries:\n")
    for log in filtered_logs:
        print(format_log_entry(log))


def follow_logs(
    persistence: DatabasePersistence,
    level: str | None = None,
    session_id: int | None = None,
) -> None:
    """Tail logs in real-time (like tail -f).

    Args:
        persistence: Database persistence instance.
        level: Optional level filter (WARNING, ERROR, CRITICAL).
        session_id: Optional session ID filter.
    """
    print("Following logs (Ctrl+C to stop)...\n")

    # Track the last log ID we've seen
    last_id = 0
    logs = persistence.load_log_entries(since=None, level=level, limit=1)
    if logs:
        last_id = logs[-1].get("id", 0)

    try:
        while True:
            # Get new logs since last check
            all_logs = persistence.load_log_entries(since=None, level=level, limit=100)

            # Filter to only logs newer than last_id
            new_logs = [log for log in all_logs if log.get("id", 0) > last_id]

            # Apply session filter if requested
            if session_id is not None:
                new_logs = [log for log in new_logs if log.get("session_id") == session_id]

            # Display new logs
            for log in new_logs:
                try:
                    print(format_log_entry(log))
                    last_id = max(last_id, log.get("id", 0))
                except Exception:  # nosec B112
                    # Skip logs that can't be decrypted
                    continue

            # Sleep before checking again
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nStopped following logs.")


def main() -> None:
    """Parse arguments and display logs."""
    parser = argparse.ArgumentParser(
        description="View encrypted logs from the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                       # Last 50 logs
  %(prog)s --level ERROR         # Only errors
  %(prog)s --limit 100           # Last 100 logs
  %(prog)s --follow              # Tail mode (like tail -f)
  %(prog)s --session 42          # Logs from session 42
  %(prog)s --follow --level ERROR  # Follow only errors
        """,
    )
    parser.add_argument(
        "--level",
        choices=["WARNING", "ERROR", "CRITICAL"],
        help="Filter by log level",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of logs to display (default: 50)",
    )
    parser.add_argument(
        "--follow",
        "-f",
        action="store_true",
        help="Follow logs in real-time (like tail -f)",
    )
    parser.add_argument(
        "--session",
        type=int,
        help="Filter by session ID",
    )

    args = parser.parse_args()

    persistence = DatabasePersistence()

    if args.follow:
        follow_logs(persistence, level=args.level, session_id=args.session)
    else:
        view_logs(
            persistence,
            level=args.level,
            limit=args.limit,
            session_id=args.session,
        )


if __name__ == "__main__":
    main()
