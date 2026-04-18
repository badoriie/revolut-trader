"""1Password MCP server for the revolut-trader vault.

Exposes four tools to Claude:
  vault_list_items   — list all items in the revolut-trader vault
  vault_get_item     — get all visible fields from one item
  vault_set_field    — update (or create) a text field in an item
  vault_validate     — check all config/strategy/risk items for missing fields

Authentication: reads OP_SERVICE_ACCOUNT_TOKEN from the environment automatically
(the op CLI picks it up without any extra flags).
"""

import json
import subprocess
import sys

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

VAULT = "revolut-trader"

# ── Expected fields per item type ─────────────────────────────────────────────

_CONFIG_REQUIRED = {
    "RISK_LEVEL",
    "BASE_CURRENCY",
    "TRADING_PAIRS",
    "DEFAULT_STRATEGY",
    "TRADING_MODE",
    "INITIAL_CAPITAL",
    "TELEGRAM_CHAT_ID",
}

_RISK_REQUIRED = {
    "MAX_POSITION_SIZE_PCT",
    "MAX_DAILY_LOSS_PCT",
    "STOP_LOSS_PCT",
    "TAKE_PROFIT_PCT",
    "MAX_OPEN_POSITIONS",
}

_STRATEGY_CORE = {"INTERVAL", "MIN_SIGNAL_STRENGTH", "ORDER_TYPE"}

_STRATEGY_EXTRA: dict[str, set[str]] = {
    "momentum": {"FAST_PERIOD", "SLOW_PERIOD", "RSI_PERIOD", "RSI_OVERBOUGHT", "RSI_OVERSOLD"},
    "breakout": {
        "LOOKBACK_PERIOD",
        "BREAKOUT_THRESHOLD",
        "RSI_PERIOD",
        "RSI_OVERBOUGHT",
        "RSI_OVERSOLD",
        "VOLUME_MULT",
    },
    "mean_reversion": {"LOOKBACK_PERIOD", "NUM_STD_DEV", "MIN_DEVIATION"},
    "market_making": {"SPREAD_THRESHOLD", "INVENTORY_TARGET"},
    "range_reversion": {
        "RSI_PERIOD",
        "BUY_ZONE",
        "SELL_ZONE",
        "RSI_CONFIRMATION_OVERSOLD",
        "RSI_CONFIRMATION_OVERBOUGHT",
        "MIN_RANGE_PCT",
    },
    "multi_strategy": {
        "MIN_CONSENSUS",
        "WEIGHT_MOMENTUM",
        "WEIGHT_BREAKOUT",
        "WEIGHT_MARKET_MAKING",
        "WEIGHT_MEAN_REVERSION",
        "WEIGHT_RANGE_REVERSION",
    },
}

# ── op CLI helpers ─────────────────────────────────────────────────────────────


def _run(*args: str) -> str | None:
    result = subprocess.run(
        ["op", *args],
        capture_output=True,
        text=True,
        timeout=15,
        stdin=subprocess.DEVNULL,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _get_item_fields(item_name: str) -> dict[str, str]:
    """Return {label: value} for all non-placeholder fields; secrets shown as <secret>."""
    raw = _run("item", "get", item_name, "--vault", VAULT, "--format", "json")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    result = {}
    for field in data.get("fields", []):
        label = field.get("label", "")
        value = field.get("value", "")
        ftype = field.get("type", "")
        if not label or label == "notesPlain":
            continue
        if ftype in ("CONCEALED", "PASSWORD"):
            result[label] = "<secret>"
        elif str(value).startswith("<") or not value:
            result[label] = "<not set>"
        else:
            result[label] = value
    return result


def _list_items() -> list[str]:
    raw = _run("item", "list", "--vault", VAULT, "--format", "json")
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return sorted(item["title"] for item in items if "title" in item)
    except (json.JSONDecodeError, KeyError):
        return []


# ── MCP server ────────────────────────────────────────────────────────────────

app = Server("onepassword-revolut-trader")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="vault_list_items",
            description="List all items in the revolut-trader 1Password vault.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="vault_get_item",
            description=(
                "Get all fields of a revolut-trader vault item. "
                "Secret/concealed fields are shown as '<secret>'; "
                "unfilled placeholder fields as '<not set>'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Full item name, e.g. 'revolut-trader-strategy-breakout'",
                    }
                },
                "required": ["item_name"],
            },
        ),
        types.Tool(
            name="vault_set_field",
            description=(
                "Create or update a TEXT field in a revolut-trader vault item. "
                "Use field_type='concealed' only for secrets (API keys, tokens). "
                "For all config/strategy/risk values use the default field_type='text'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Full vault item name"},
                    "field_name": {"type": "string", "description": "Field label (e.g. VOLUME_MULT)"},
                    "value": {"type": "string", "description": "New value to store"},
                    "field_type": {
                        "type": "string",
                        "enum": ["text", "concealed"],
                        "default": "text",
                        "description": "Field storage type; use 'text' for config values",
                    },
                },
                "required": ["item_name", "field_name", "value"],
            },
        ),
        types.Tool(
            name="vault_validate",
            description=(
                "Validate all revolut-trader vault items against expected schemas. "
                "Reports missing required fields per item and flags placeholder values."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "vault_list_items":
        items = _list_items()
        if not items:
            text = "No items found (check OP_SERVICE_ACCOUNT_TOKEN is set)."
        else:
            text = f"Items in vault '{VAULT}' ({len(items)}):\n" + "\n".join(f"  • {i}" for i in items)
        return [types.TextContent(type="text", text=text)]

    if name == "vault_get_item":
        item_name = arguments["item_name"]
        fields = _get_item_fields(item_name)
        if not fields:
            text = f"Item '{item_name}' not found or empty."
        else:
            lines = [f"Fields for '{item_name}':"]
            for label, value in sorted(fields.items()):
                lines.append(f"  {label}: {value}")
            text = "\n".join(lines)
        return [types.TextContent(type="text", text=text)]

    if name == "vault_set_field":
        item_name = arguments["item_name"]
        field_name = arguments["field_name"]
        value = arguments["value"]
        field_type = arguments.get("field_type", "text")
        op_field = f"{field_name}[{field_type}]={value}"
        result = _run("item", "edit", item_name, "--vault", VAULT, op_field)
        if result is not None:
            text = f"✓ Set {item_name} → {field_name} = {value!r} (type: {field_type})"
        else:
            text = f"✗ Failed to set {field_name} in {item_name}. Check op CLI auth and item name."
        return [types.TextContent(type="text", text=text)]

    if name == "vault_validate":
        lines: list[str] = []
        all_ok = True

        items = _list_items()

        # Config items (env-specific)
        for env in ("dev", "int", "prod"):
            item = f"revolut-trader-config-{env}"
            if item not in items:
                lines.append(f"✗ MISSING ITEM: {item}")
                all_ok = False
                continue
            fields = _get_item_fields(item)
            present = {k for k, v in fields.items() if v not in ("<not set>", "")}
            missing = _CONFIG_REQUIRED - present
            if missing:
                lines.append(f"✗ {item}: missing required fields: {sorted(missing)}")
                all_ok = False
            else:
                lines.append(f"✓ {item}")

        # Credentials items
        for env, required in {
            "dev": {"DATABASE_ENCRYPTION_KEY", "TELEGRAM_BOT_TOKEN"},
            "int": {"REVOLUT_API_KEY", "REVOLUT_PRIVATE_KEY", "REVOLUT_PUBLIC_KEY", "DATABASE_ENCRYPTION_KEY", "TELEGRAM_BOT_TOKEN"},
            "prod": {"REVOLUT_API_KEY", "REVOLUT_PRIVATE_KEY", "REVOLUT_PUBLIC_KEY", "DATABASE_ENCRYPTION_KEY", "TELEGRAM_BOT_TOKEN"},
        }.items():
            item = f"revolut-trader-credentials-{env}"
            if item not in items:
                lines.append(f"✗ MISSING ITEM: {item}")
                all_ok = False
                continue
            fields = _get_item_fields(item)
            missing = required - set(fields.keys())
            if missing:
                lines.append(f"✗ {item}: missing fields: {sorted(missing)}")
                all_ok = False
            else:
                lines.append(f"✓ {item}")

        # Risk items
        for level in ("conservative", "moderate", "aggressive"):
            item = f"revolut-trader-risk-{level}"
            if item not in items:
                lines.append(f"✗ MISSING ITEM: {item}")
                all_ok = False
                continue
            fields = _get_item_fields(item)
            present = {k for k, v in fields.items() if v not in ("<not set>", "")}
            missing = _RISK_REQUIRED - present
            if missing:
                lines.append(f"✗ {item}: missing fields: {sorted(missing)}")
                all_ok = False
            else:
                lines.append(f"✓ {item}")

        # Strategy items
        for strategy, extra in _STRATEGY_EXTRA.items():
            item = f"revolut-trader-strategy-{strategy}"
            if item not in items:
                lines.append(f"✗ MISSING ITEM: {item}")
                all_ok = False
                continue
            fields = _get_item_fields(item)
            present = {k for k, v in fields.items() if v not in ("<not set>", "")}
            required_all = _STRATEGY_CORE | extra
            # STOP_LOSS_PCT / TAKE_PROFIT_PCT optional for multi_strategy
            if strategy != "multi_strategy":
                required_all |= {"STOP_LOSS_PCT", "TAKE_PROFIT_PCT"}
            missing = required_all - present
            if missing:
                lines.append(f"✗ {item}: missing fields: {sorted(missing)}")
                all_ok = False
            else:
                lines.append(f"✓ {item}")

        summary = "All vault items valid." if all_ok else "Issues found — see above."
        text = "\n".join(lines) + f"\n\n{summary}"
        return [types.TextContent(type="text", text=text)]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
