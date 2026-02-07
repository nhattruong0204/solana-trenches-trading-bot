# Telegram Bot Development Guide

> A comprehensive guide for building Telegram bots in this repository. This document captures the patterns, conventions, and features used in the existing bot implementations to help Copilot agents replicate similar functionality.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Patterns](#architecture-patterns)
3. [Bot Setup & Initialization](#bot-setup--initialization)
4. [Command Handler Pattern](#command-handler-pattern)
5. [Event Handling](#event-handling)
6. [Interactive Buttons & Menus](#interactive-buttons--menus)
7. [Notification System](#notification-system)
8. [State Management](#state-management)
9. [Authentication & Authorization](#authentication--authorization)
10. [Error Handling](#error-handling)
11. [Complete Implementation Template](#complete-implementation-template)
12. [Testing Telegram Bots](#testing-telegram-bots)

---

## Overview

This repository implements multiple Telegram bot patterns:

1. **NotificationBot** (`src/notification_bot.py`) - Admin bot with commands, menus, and notifications
2. **TelegramController** (`src/controller.py`) - Remote control interface
3. **CommercialBot** (`src/commercial_bot.py`) - Premium features integration

### Key Technologies

- **Telethon**: Async Telegram client library
- **Bot API**: Via BotFather token for bot operations
- **User Client**: For monitoring channels and advanced operations

---

## Architecture Patterns

### 1. Bot Class Structure

```python
"""
Module docstring describing the bot's purpose.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel, Chat
from telethon.tl.custom import Button

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)


class YourBot:
    """
    Brief description of what this bot does.
    
    Commands:
        /start - Description
        /help - Description
        /command - Description
    """
    
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        bot_token: str,
        settings: "Settings",
        admin_user_id: int,
    ) -> None:
        """
        Initialize the bot.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API hash
            bot_token: Bot token from BotFather
            settings: Application settings
            admin_user_id: Telegram user ID of admin
        """
        self._api_id = api_id
        self._api_hash = api_hash
        self._bot_token = bot_token
        self._settings = settings
        self._admin_user_id = admin_user_id
        
        self._client: Optional[TelegramClient] = None
        self._initialized = False
        
        # Bot state variables
        self._awaiting_input = False
    
    @property
    def is_initialized(self) -> bool:
        """Check if bot is initialized."""
        return self._initialized
```

### 2. Dependency Injection Pattern

Always pass dependencies explicitly:

```python
class YourBot:
    def __init__(
        self,
        client: TelegramClient,
        settings: Settings,
        state_manager: StateManager,
        notification_handler: NotificationHandler,
    ) -> None:
        self._client = client
        self._settings = settings
        self._state = state_manager
        self._notifier = notification_handler
```

### 3. Async Context Manager Pattern

For bots with lifecycle management:

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

@asynccontextmanager
async def create_bot(settings: Settings) -> AsyncIterator[YourBot]:
    """
    Create and manage bot lifecycle.
    
    Usage:
        async with create_bot(settings) as bot:
            await bot.run()
    """
    bot = YourBot(settings)
    await bot.start()
    try:
        yield bot
    finally:
        await bot.stop()
```

---

## Bot Setup & Initialization

### 1. Bot Client Creation

```python
async def start(self) -> None:
    """Start the bot client."""
    if self._initialized:
        return
    
    # Create bot client with in-memory session
    self._client = TelegramClient(
        StringSession(),  # Use in-memory session for bots
        self._api_id,
        self._api_hash,
    )
    
    # Start with bot token
    await self._client.start(bot_token=self._bot_token)
    
    # Get bot info
    me = await self._client.get_me()
    logger.info(f"✅ Bot started: @{me.username}")
    
    # Register event handlers
    self._register_handlers()
    
    # Set up bot commands menu (appears in Telegram UI)
    await self._setup_bot_commands()
    
    self._initialized = True
```

### 2. Bot Commands Menu Setup

This creates the command menu that appears when users type "/" in Telegram:

```python
async def _setup_bot_commands(self) -> None:
    """Set up bot commands for the menu."""
    from telethon.tl.functions.bots import SetBotCommandsRequest
    from telethon.tl.types import BotCommand
    
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="menu", description="Show interactive menu"),
        BotCommand(command="status", description="Check bot status"),
        BotCommand(command="positions", description="View open positions"),
        BotCommand(command="help", description="Show all commands"),
    ]
    
    try:
        await self._client(SetBotCommandsRequest(
            scope=None,  # Global scope
            lang_code="en",
            commands=commands
        ))
        logger.info("✅ Bot commands menu set up")
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}")
```

### 3. Shutdown Handling

```python
async def stop(self) -> None:
    """Stop the bot client."""
    if not self._initialized:
        return
    
    logger.info("Stopping bot...")
    
    # Clean up resources
    if self._client and self._client.is_connected():
        await self._client.disconnect()
    
    self._initialized = False
    logger.info("Bot stopped")
```

---

## Command Handler Pattern

### 1. Event Handler Registration

```python
def _register_handlers(self) -> None:
    """Register all event handlers."""
    if not self._client:
        return
    
    # Handle all incoming messages
    @self._client.on(events.NewMessage(chats=[self._admin_user_id]))
    async def handle_message(event: events.NewMessage.Event) -> None:
        """Handle incoming messages from admin."""
        try:
            await self._handle_message(event)
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await self._send_to_admin("❌ An error occurred processing your message.")
    
    # Handle callback queries (button clicks)
    @self._client.on(events.CallbackQuery)
    async def handle_callback(event: events.CallbackQuery.Event) -> None:
        """Handle button callbacks."""
        try:
            await self._handle_callback(event)
        except Exception as e:
            logger.error(f"Error handling callback: {e}", exc_info=True)
            await event.answer("❌ Error processing action", alert=True)
```

### 2. Message Dispatcher Pattern

```python
async def _handle_message(self, event: events.NewMessage.Event) -> None:
    """Main message handler dispatcher."""
    message = event.message
    text = message.text.strip()
    
    # Handle stateful input (e.g., awaiting wallet address)
    if self._awaiting_wallet:
        await self._handle_wallet_input(text)
        return
    
    # Handle commands (start with /)
    if text.startswith("/"):
        await self._handle_command(text)
        return
    
    # Handle plain text
    await self._send_to_admin(
        "❓ Send a command starting with / or use /menu for options."
    )
```

### 3. Command Routing

```python
async def _handle_command(self, text: str) -> None:
    """Route commands to appropriate handlers."""
    parts = text.split(maxsplit=1)
    command = parts[0].lower().split("@")[0]  # Remove @botname if present
    args = parts[1] if len(parts) > 1 else ""
    
    # Command mapping
    handlers = {
        "/start": self._cmd_start,
        "/help": self._cmd_help,
        "/menu": self._cmd_menu,
        "/status": self._cmd_status,
        "/positions": self._cmd_positions,
        "/settings": self._cmd_settings,
        "/setsize": self._cmd_set_size,
        "/pause": self._cmd_pause,
        "/resume": self._cmd_resume,
    }
    
    handler = handlers.get(command)
    if handler:
        try:
            await handler(args)
        except Exception as e:
            logger.error(f"Error in command {command}: {e}", exc_info=True)
            await self._send_to_admin(f"❌ Error executing {command}")
    else:
        await self._send_to_admin(
            f"❓ Unknown command: `{command}`\n\nUse /help for available commands."
        )
```

### 4. Command Handler Implementation

```python
async def _cmd_start(self, args: str) -> None:
    """Handle /start command."""
    message = (
        "🤖 *Welcome to Your Bot*\n\n"
        "I can help you with:\n"
        "• Feature 1\n"
        "• Feature 2\n"
        "• Feature 3\n\n"
        "Use /menu for interactive options or /help for commands."
    )
    await self._send_to_admin(message)

async def _cmd_help(self, args: str) -> None:
    """Handle /help command."""
    message = (
        "📚 *Available Commands*\n\n"
        "*Information:*\n"
        "/start - Welcome message\n"
        "/status - Check status\n"
        "/help - This message\n\n"
        "*Configuration:*\n"
        "/setsize <value> - Set size\n"
        "/settings - View settings\n\n"
        "*Control:*\n"
        "/pause - Pause operations\n"
        "/resume - Resume operations\n"
    )
    await self._send_to_admin(message)

async def _cmd_status(self, args: str) -> None:
    """Handle /status command."""
    # Gather status information
    uptime = self._calculate_uptime() if self._start_time else "Not started"
    
    message = (
        "📊 *Bot Status*\n\n"
        f"• Status: `{'Running' if self._is_running else 'Stopped'}`\n"
        f"• Uptime: `{uptime}`\n"
        f"• Operations: `{self._operation_count}`\n"
    )
    await self._send_to_admin(message)

async def _cmd_set_size(self, args: str) -> None:
    """Handle /setsize command with argument validation."""
    if not args:
        await self._send_to_admin(
            "❌ *Missing argument*\n\n"
            "Usage: `/setsize <value>`\n"
            "Example: `/setsize 0.1`"
        )
        return
    
    try:
        value = float(args)
        if not 0.001 <= value <= 100:
            raise ValueError("Value out of range")
        
        self._size = value
        await self._send_to_admin(
            f"✅ Size updated to `{value}`"
        )
    except ValueError as e:
        await self._send_to_admin(
            f"❌ *Invalid value*\n\n"
            f"Please provide a number between 0.001 and 100.\n"
            f"Example: `/setsize 0.1`"
        )
```

---

## Event Handling

### 1. Callback Query Handler (Button Clicks)

```python
async def _handle_callback(self, event: events.CallbackQuery.Event) -> None:
    """Handle button callback queries."""
    sender = await event.get_sender()
    
    # Authorization check
    if not sender or sender.id != self._admin_user_id:
        await event.answer("⚠️ You are not authorized", alert=True)
        return
    
    data = event.data.decode('utf-8')
    
    # Always acknowledge the callback
    await event.answer()
    
    # Map callback data to handlers
    callback_handlers = {
        "cmd_status": lambda: self._cmd_status(""),
        "cmd_positions": lambda: self._cmd_positions(""),
        "cmd_help": lambda: self._cmd_help(""),
        "setting_option1": lambda: self._handle_setting_option1(),
        "setting_option2": lambda: self._handle_setting_option2(),
    }
    
    handler = callback_handlers.get(data)
    if handler:
        try:
            await handler()
        except Exception as e:
            logger.error(f"Error in callback {data}: {e}", exc_info=True)
            await self._send_to_admin("❌ Error processing action")
    else:
        logger.warning(f"Unknown callback: {data}")
```

### 2. Pattern-Based Event Handlers

For monitoring specific patterns in channels:

```python
def _register_channel_monitors(self) -> None:
    """Register handlers for channel monitoring."""
    
    # Monitor specific channel for specific pattern
    @self._client.on(events.NewMessage(chats=self._channel_entity))
    async def handle_channel_message(event: events.NewMessage.Event) -> None:
        """Monitor channel for specific messages."""
        message = event.message
        text = message.text
        
        if "SIGNAL DETECTED" in text:
            await self._handle_signal(message)
        elif "ALERT" in text:
            await self._handle_alert(message)
```

---

## Interactive Buttons & Menus

### 1. Button Types

Telethon supports several button types:

```python
from telethon.tl.custom import Button

# Inline buttons (appear below message)
inline_button = Button.inline(text="Click Me", data=b"callback_data")

# URL buttons (open a link)
url_button = Button.url(text="Visit", url="https://example.com")

# Switch inline buttons
switch_button = Button.switch_inline(text="Share", query="query")
```

### 2. Menu Pattern

```python
def _get_menu_buttons(self) -> list:
    """
    Get the main menu buttons.
    
    Returns a 2D list where each inner list is a row of buttons.
    """
    return [
        # Row 1 - Two buttons side by side
        [
            Button.inline("📊 Status", b"cmd_status"),
            Button.inline("📈 Positions", b"cmd_positions"),
        ],
        # Row 2
        [
            Button.inline("⚙️ Settings", b"cmd_settings"),
            Button.inline("📊 Stats", b"cmd_stats"),
        ],
        # Row 3 - Single button
        [
            Button.inline("❓ Help", b"cmd_help"),
        ],
    ]

async def _cmd_menu(self, args: str) -> None:
    """Show interactive menu with buttons."""
    message = (
        "🤖 *BOT MENU*\n\n"
        "Select an option below:"
    )
    
    await self._send_to_admin_with_buttons(message, self._get_menu_buttons())

async def _send_to_admin_with_buttons(
    self, 
    message: str, 
    buttons: list
) -> None:
    """Send message to admin with inline buttons."""
    if not self._client:
        return
    
    try:
        await self._client.send_message(
            self._admin_user_id,
            message,
            parse_mode="markdown",
            buttons=buttons,
        )
    except Exception as e:
        logger.error(f"Failed to send message with buttons: {e}")
```

### 3. Dynamic Button Generation

For toggleable settings:

```python
def _get_strategy_buttons(self) -> list:
    """Generate buttons for strategy toggles."""
    buttons = []
    
    for strategy_id, strategy in self._strategies.items():
        is_enabled = self._strategy_state.get(strategy_id, False)
        emoji = "✅" if is_enabled else "❌"
        text = f"{emoji} {strategy.name}"
        
        buttons.append([
            Button.inline(text, f"toggle_strategy_{strategy_id}".encode())
        ])
    
    # Add back button
    buttons.append([
        Button.inline("« Back to Menu", b"cmd_menu")
    ])
    
    return buttons

async def _handle_callback(self, event: events.CallbackQuery.Event) -> None:
    """Handle button callbacks."""
    # ... authorization checks ...
    
    data = event.data.decode('utf-8')
    await event.answer()
    
    # Handle toggle callbacks
    if data.startswith("toggle_strategy_"):
        strategy_id = data.replace("toggle_strategy_", "")
        await self._toggle_strategy(strategy_id)
        return
    
    # ... other handlers ...

async def _toggle_strategy(self, strategy_id: str) -> None:
    """Toggle a strategy on/off."""
    current = self._strategy_state.get(strategy_id, False)
    self._strategy_state[strategy_id] = not current
    
    # Save state
    await self._save_strategy_state()
    
    # Refresh the strategies menu
    await self._cmd_strategies("")
```

### 4. Pagination Pattern

For long lists:

```python
async def _send_paginated_list(
    self,
    items: list,
    page: int = 0,
    items_per_page: int = 5,
    title: str = "Items"
) -> None:
    """Send paginated list with navigation buttons."""
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = items[start_idx:end_idx]
    
    # Build message
    message = f"*{title}* (Page {page + 1}/{total_pages})\n\n"
    for i, item in enumerate(page_items, start=start_idx + 1):
        message += f"{i}. {item}\n"
    
    # Build navigation buttons
    buttons = []
    nav_row = []
    
    if page > 0:
        nav_row.append(Button.inline("« Prev", f"page_{page-1}".encode()))
    if page < total_pages - 1:
        nav_row.append(Button.inline("Next »", f"page_{page+1}".encode()))
    
    if nav_row:
        buttons.append(nav_row)
    
    buttons.append([Button.inline("« Back", b"cmd_menu")])
    
    await self._send_to_admin_with_buttons(message, buttons)
```

---

## Notification System

### 1. Basic Notification Pattern

```python
async def _send_to_admin(self, message: str) -> None:
    """Send message to admin user."""
    if not self._client:
        logger.warning("Cannot send message: client not initialized")
        return
    
    try:
        await self._client.send_message(
            self._admin_user_id,
            message,
            parse_mode="markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send message to admin: {e}")
```

### 2. Channel/Group Notifications

```python
async def _send_notification(self, message: str) -> None:
    """
    Send notification to channel or admin.
    
    If notification channel is configured, sends there.
    Otherwise, sends to admin DM.
    """
    if not self._client:
        return
    
    target = self._channel_entity if self._channel_entity else self._admin_user_id
    
    try:
        await self._client.send_message(
            target,
            message,
            parse_mode="markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
```

### 3. Structured Notifications

```python
async def notify_trade_executed(
    self,
    token_symbol: str,
    token_address: str,
    amount: float,
    action: str,  # "buy" or "sell"
) -> None:
    """Send structured trade notification."""
    emoji = "🟢" if action == "buy" else "🔴"
    action_text = "BUY" if action == "buy" else "SELL"
    
    message = (
        f"{emoji} *{action_text} EXECUTED*\n\n"
        f"Token: `${token_symbol}`\n"
        f"Address: `{token_address[:8]}...{token_address[-6:]}`\n"
        f"Amount: `{amount} SOL`\n"
        f"Time: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`"
    )
    
    await self._send_notification(message)

async def notify_error(
    self,
    error_type: str,
    error_message: str,
    context: dict = None
) -> None:
    """Send error notification to admin."""
    message = (
        f"⚠️ *ERROR: {error_type}*\n\n"
        f"{error_message}\n"
    )
    
    if context:
        message += "\n*Context:*\n"
        for key, value in context.items():
            message += f"• {key}: `{value}`\n"
    
    await self._send_to_admin(message)
```

### 4. Clickable Links in Messages

```python
def _format_token_link(
    self,
    token_symbol: str,
    message_id: int,
    channel_username: str = "yourchannel"
) -> str:
    """
    Create clickable token symbol that links to original message.
    
    Args:
        token_symbol: e.g., "TRUMP"
        message_id: Telegram message ID
        channel_username: Channel username without @
    
    Returns:
        Markdown formatted link: [$TRUMP](https://t.me/channel/12345)
    """
    url = f"https://t.me/{channel_username}/{message_id}"
    return f"[${token_symbol}]({url})"

async def send_pnl_report(self, signals: list) -> None:
    """Send PnL report with clickable token links."""
    message = "*PnL Report*\n\n"
    
    for signal in signals:
        token_link = self._format_token_link(
            signal.symbol,
            signal.message_id
        )
        message += f"• {token_link}: `{signal.multiplier}x`\n"
    
    await self._send_to_admin(message)
```

---

## State Management

### 1. Stateful Input Pattern

For multi-step interactions:

```python
class YourBot:
    def __init__(self, ...):
        # ... other init ...
        self._awaiting_wallet = False
        self._awaiting_confirmation = False
        self._pending_action = None

async def _cmd_set_wallet(self, args: str) -> None:
    """Initiate wallet input."""
    if args:
        # Direct input provided
        await self._process_wallet(args)
    else:
        # Ask for input
        await self._send_to_admin(
            "Please send your wallet address:"
        )
        self._awaiting_wallet = True

async def _handle_message(self, event: events.NewMessage.Event) -> None:
    """Main message handler with state checks."""
    text = event.message.text.strip()
    
    # Check for stateful input handlers first
    if self._awaiting_wallet:
        await self._handle_wallet_input(text)
        return
    
    if self._awaiting_confirmation:
        await self._handle_confirmation(text)
        return
    
    # Normal command processing
    if text.startswith("/"):
        await self._handle_command(text)
        return

async def _handle_wallet_input(self, text: str) -> None:
    """Handle wallet address input."""
    self._awaiting_wallet = False  # Reset state
    
    # Validate input
    if not self._is_valid_wallet(text):
        await self._send_to_admin(
            "❌ Invalid wallet address. Please try again with /setwallet"
        )
        return
    
    # Process valid input
    await self._process_wallet(text)

def _is_valid_wallet(self, address: str) -> bool:
    """Validate Solana wallet address."""
    import re
    pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
    return bool(pattern.match(address))
```

### 2. Persistent State Storage

```python
import json
import aiofiles
from pathlib import Path

class YourBot:
    def __init__(self, ...):
        self._state_file = Path("bot_state.json")
        self._state = {}

async def _load_state(self) -> None:
    """Load bot state from file."""
    if not self._state_file.exists():
        self._state = {}
        return
    
    try:
        async with aiofiles.open(self._state_file, 'r') as f:
            content = await f.read()
            self._state = json.loads(content)
        logger.info(f"State loaded: {len(self._state)} items")
    except Exception as e:
        logger.error(f"Failed to load state: {e}")
        self._state = {}

async def _save_state(self) -> None:
    """Save bot state to file."""
    try:
        async with aiofiles.open(self._state_file, 'w') as f:
            await f.write(json.dumps(self._state, indent=2))
        logger.debug("State saved successfully")
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

async def _update_setting(self, key: str, value: any) -> None:
    """Update a setting and persist state."""
    self._state[key] = value
    await self._save_state()
```

---

## Authentication & Authorization

### 1. Admin-Only Commands

```python
def _is_admin(self, user_id: int) -> bool:
    """Check if user is admin."""
    return user_id == self._admin_user_id

async def _handle_message(self, event: events.NewMessage.Event) -> None:
    """Handle messages with authorization."""
    sender = await event.get_sender()
    
    if not sender or not self._is_admin(sender.id):
        await event.respond("⚠️ You are not authorized to use this bot.")
        return
    
    # Process message
    await self._process_admin_message(event)
```

### 2. Multi-User Authorization

```python
class YourBot:
    def __init__(self, ...):
        # List of authorized user IDs
        self._authorized_users = [
            self._admin_user_id,
            # ... other user IDs from config
        ]

def _is_authorized(self, user_id: int) -> bool:
    """Check if user is authorized."""
    return user_id in self._authorized_users

async def _handle_callback(self, event: events.CallbackQuery.Event) -> None:
    """Handle button callbacks with auth check."""
    sender = await event.get_sender()
    
    if not sender or not self._is_authorized(sender.id):
        await event.answer("⚠️ You are not authorized", alert=True)
        return
    
    # Process callback
    data = event.data.decode('utf-8')
    # ... handle callback ...
```

### 3. Role-Based Access

```python
from enum import Enum

class UserRole(Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"

class YourBot:
    def __init__(self, ...):
        self._user_roles = {
            self._admin_user_id: UserRole.ADMIN,
            # ... other users
        }

def _get_user_role(self, user_id: int) -> UserRole:
    """Get user role."""
    return self._user_roles.get(user_id, UserRole.USER)

def _requires_role(self, required_role: UserRole):
    """Decorator for role-based access control."""
    def decorator(func):
        async def wrapper(self, args: str, user_id: int = None):
            user_role = self._get_user_role(user_id or self._admin_user_id)
            
            # Role hierarchy: ADMIN > MODERATOR > USER
            role_levels = {
                UserRole.USER: 1,
                UserRole.MODERATOR: 2,
                UserRole.ADMIN: 3,
            }
            
            if role_levels[user_role] < role_levels[required_role]:
                await self._send_to_admin(
                    f"❌ This command requires {required_role.value} role"
                )
                return
            
            return await func(self, args)
        return wrapper
    return decorator

# Usage:
@_requires_role(UserRole.ADMIN)
async def _cmd_reset(self, args: str) -> None:
    """Admin-only reset command."""
    # ... implementation ...
```

---

## Error Handling

### 1. Graceful Error Recovery

```python
async def _handle_command(self, text: str) -> None:
    """Handle command with error recovery."""
    parts = text.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    handler = self._command_handlers.get(command)
    if not handler:
        await self._send_to_admin(
            f"❓ Unknown command: `{command}`"
        )
        return
    
    try:
        await handler(args)
    except ValueError as e:
        await self._send_to_admin(
            f"❌ *Invalid input*\n\n{str(e)}"
        )
    except PermissionError as e:
        await self._send_to_admin(
            f"⚠️ *Permission denied*\n\n{str(e)}"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in command {command}: {e}",
            exc_info=True
        )
        await self._send_to_admin(
            f"❌ An unexpected error occurred.\n\n"
            f"Command: `{command}`\n"
            f"Error: `{type(e).__name__}`"
        )
```

### 2. Rate Limiting

```python
import time
from collections import defaultdict

class YourBot:
    def __init__(self, ...):
        self._last_command_time = defaultdict(float)
        self._rate_limit_seconds = 1.0  # Minimum time between commands

async def _check_rate_limit(self, user_id: int) -> bool:
    """Check if user is rate limited."""
    now = time.time()
    last_time = self._last_command_time[user_id]
    
    if now - last_time < self._rate_limit_seconds:
        return False
    
    self._last_command_time[user_id] = now
    return True

async def _handle_command(self, text: str, user_id: int) -> None:
    """Handle command with rate limiting."""
    if not await self._check_rate_limit(user_id):
        await self._send_to_admin(
            "⏳ Please wait a moment before sending another command."
        )
        return
    
    # Process command
    # ...
```

### 3. Retry Logic for External Calls

```python
import asyncio
from typing import TypeVar, Callable

T = TypeVar('T')

async def retry_async(
    func: Callable[..., T],
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
) -> T:
    """
    Retry an async function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier
    
    Returns:
        Function result
    
    Raises:
        Last exception if all attempts fail
    """
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt < max_attempts - 1:
                wait_time = delay * (backoff ** attempt)
                logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"All {max_attempts} attempts failed")
    
    raise last_exception

# Usage:
async def _send_trade_notification(self, trade_data: dict) -> None:
    """Send trade notification with retry."""
    async def send():
        await self._client.send_message(
            self._notification_channel,
            self._format_trade_message(trade_data)
        )
    
    try:
        await retry_async(send, max_attempts=3)
    except Exception as e:
        logger.error(f"Failed to send notification after retries: {e}")
```

---

## Complete Implementation Template

Here's a complete template combining all patterns:

```python
"""
Your Bot Module - Brief description.

This module implements a Telegram bot for [purpose].
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

import aiofiles
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel, Chat
from telethon.tl.custom import Button

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)


class YourBot:
    """
    Telegram bot for [purpose].
    
    Commands:
        /start - Welcome message
        /menu - Interactive menu
        /status - Bot status
        /settings - View settings
        /help - Show all commands
    """
    
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        bot_token: str,
        settings: "Settings",
        admin_user_id: int,
        notification_channel: Optional[str] = None,
    ) -> None:
        """
        Initialize the bot.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API hash
            bot_token: Bot token from BotFather
            settings: Application settings
            admin_user_id: Telegram user ID of admin
            notification_channel: Optional channel for notifications
        """
        self._api_id = api_id
        self._api_hash = api_hash
        self._bot_token = bot_token
        self._settings = settings
        self._admin_user_id = admin_user_id
        self._notification_channel = notification_channel
        
        # Telegram client
        self._client: Optional[TelegramClient] = None
        self._channel_entity: Optional[Channel | Chat] = None
        self._initialized = False
        
        # Bot state
        self._state_file = Path("your_bot_state.json")
        self._state: dict[str, Any] = {}
        self._awaiting_input = False
        
        # Rate limiting
        self._last_command_time = defaultdict(float)
        self._rate_limit_seconds = 1.0
        
        # Stats
        self._start_time: Optional[datetime] = None
        self._command_count = 0
    
    @property
    def is_initialized(self) -> bool:
        """Check if bot is initialized."""
        return self._initialized
    
    # ==================== Lifecycle ====================
    
    async def start(self) -> None:
        """Start the bot client."""
        if self._initialized:
            return
        
        logger.info("Starting bot...")
        
        # Create bot client
        self._client = TelegramClient(
            StringSession(),
            self._api_id,
            self._api_hash,
        )
        
        await self._client.start(bot_token=self._bot_token)
        
        # Get bot info
        me = await self._client.get_me()
        logger.info(f"✅ Bot started: @{me.username}")
        
        # Load state
        await self._load_state()
        
        # Set up bot commands
        await self._setup_bot_commands()
        
        # Register event handlers
        self._register_handlers()
        
        # Resolve notification channel if configured
        if self._notification_channel:
            try:
                self._channel_entity = await self._client.get_entity(
                    self._notification_channel
                )
                logger.info("✅ Notification channel resolved")
            except Exception as e:
                logger.warning(f"Could not resolve channel: {e}")
        
        self._initialized = True
        self._start_time = datetime.now(timezone.utc)
        
        # Send startup notification
        await self._send_to_admin(
            "🤖 *Bot Started*\n\n"
            "Bot is now online and ready to receive commands.\n"
            "Use /menu for options."
        )
    
    async def stop(self) -> None:
        """Stop the bot client."""
        if not self._initialized:
            return
        
        logger.info("Stopping bot...")
        
        # Save state
        await self._save_state()
        
        # Disconnect client
        if self._client and self._client.is_connected():
            await self._client.disconnect()
        
        self._initialized = False
        logger.info("Bot stopped")
    
    # ==================== State Management ====================
    
    async def _load_state(self) -> None:
        """Load bot state from file."""
        if not self._state_file.exists():
            self._state = {}
            return
        
        try:
            async with aiofiles.open(self._state_file, 'r') as f:
                content = await f.read()
                self._state = json.loads(content)
            logger.info(f"State loaded: {len(self._state)} items")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            self._state = {}
    
    async def _save_state(self) -> None:
        """Save bot state to file."""
        try:
            async with aiofiles.open(self._state_file, 'w') as f:
                await f.write(json.dumps(self._state, indent=2))
            logger.debug("State saved")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    # ==================== Event Handlers ====================
    
    def _register_handlers(self) -> None:
        """Register all event handlers."""
        if not self._client:
            return
        
        @self._client.on(events.NewMessage(chats=[self._admin_user_id]))
        async def handle_message(event: events.NewMessage.Event) -> None:
            try:
                await self._handle_message(event)
            except Exception as e:
                logger.error(f"Error handling message: {e}", exc_info=True)
                await self._send_to_admin("❌ Error processing message")
        
        @self._client.on(events.CallbackQuery)
        async def handle_callback(event: events.CallbackQuery.Event) -> None:
            try:
                await self._handle_callback(event)
            except Exception as e:
                logger.error(f"Error handling callback: {e}", exc_info=True)
                await event.answer("❌ Error", alert=True)
    
    async def _handle_message(self, event: events.NewMessage.Event) -> None:
        """Main message handler."""
        message = event.message
        text = message.text.strip()
        
        # Get sender
        sender = await event.get_sender()
        if not sender or sender.id != self._admin_user_id:
            await event.respond("⚠️ You are not authorized")
            return
        
        # Check rate limit
        if not await self._check_rate_limit(sender.id):
            await self._send_to_admin("⏳ Please wait...")
            return
        
        # Handle stateful input
        if self._awaiting_input:
            await self._handle_input(text)
            return
        
        # Handle commands
        if text.startswith("/"):
            await self._handle_command(text)
            return
        
        # Default response
        await self._send_to_admin(
            "Send a command (start with /) or use /menu"
        )
    
    async def _handle_command(self, text: str) -> None:
        """Route commands to handlers."""
        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""
        
        handlers = {
            "/start": self._cmd_start,
            "/menu": self._cmd_menu,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/settings": self._cmd_settings,
        }
        
        handler = handlers.get(command)
        if handler:
            self._command_count += 1
            try:
                await handler(args)
            except Exception as e:
                logger.error(f"Error in {command}: {e}", exc_info=True)
                await self._send_to_admin(f"❌ Error executing {command}")
        else:
            await self._send_to_admin(
                f"❓ Unknown command: `{command}`\n\nUse /help for commands."
            )
    
    async def _handle_callback(self, event: events.CallbackQuery.Event) -> None:
        """Handle button callbacks."""
        sender = await event.get_sender()
        
        if not sender or sender.id != self._admin_user_id:
            await event.answer("⚠️ Not authorized", alert=True)
            return
        
        data = event.data.decode('utf-8')
        await event.answer()
        
        # Map callbacks to handlers
        callback_handlers = {
            "cmd_status": lambda: self._cmd_status(""),
            "cmd_menu": lambda: self._cmd_menu(""),
            "cmd_help": lambda: self._cmd_help(""),
        }
        
        handler = callback_handlers.get(data)
        if handler:
            await handler()
    
    # ==================== Commands ====================
    
    async def _cmd_start(self, args: str) -> None:
        """Handle /start command."""
        message = (
            "🤖 *Your Bot*\n\n"
            "Welcome! I can help you with [features].\n\n"
            "Use /menu for options or /help for commands."
        )
        await self._send_to_admin(message)
    
    async def _cmd_menu(self, args: str) -> None:
        """Show interactive menu."""
        message = "🤖 *BOT MENU*\n\nSelect an option:"
        buttons = [
            [
                Button.inline("📊 Status", b"cmd_status"),
                Button.inline("❓ Help", b"cmd_help"),
            ],
        ]
        await self._send_to_admin_with_buttons(message, buttons)
    
    async def _cmd_help(self, args: str) -> None:
        """Show help message."""
        message = (
            "📚 *Available Commands*\n\n"
            "/start - Welcome message\n"
            "/menu - Interactive menu\n"
            "/status - Bot status\n"
            "/help - This message\n"
        )
        await self._send_to_admin(message)
    
    async def _cmd_status(self, args: str) -> None:
        """Show bot status."""
        uptime = self._calculate_uptime()
        
        message = (
            "📊 *Bot Status*\n\n"
            f"• Uptime: `{uptime}`\n"
            f"• Commands: `{self._command_count}`\n"
        )
        await self._send_to_admin(message)
    
    async def _cmd_settings(self, args: str) -> None:
        """Show current settings."""
        message = (
            "⚙️ *Settings*\n\n"
            f"• Setting 1: `{self._state.get('setting1', 'default')}`\n"
            f"• Setting 2: `{self._state.get('setting2', 'default')}`\n"
        )
        await self._send_to_admin(message)
    
    # ==================== Helpers ====================
    
    async def _check_rate_limit(self, user_id: int) -> bool:
        """Check rate limit for user."""
        now = time.time()
        last_time = self._last_command_time[user_id]
        
        if now - last_time < self._rate_limit_seconds:
            return False
        
        self._last_command_time[user_id] = now
        return True
    
    def _calculate_uptime(self) -> str:
        """Calculate bot uptime."""
        if not self._start_time:
            return "Not started"
        
        delta = datetime.now(timezone.utc) - self._start_time
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}m"
    
    async def _send_to_admin(self, message: str) -> None:
        """Send message to admin."""
        if not self._client:
            return
        
        try:
            await self._client.send_message(
                self._admin_user_id,
                message,
                parse_mode="markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send to admin: {e}")
    
    async def _send_to_admin_with_buttons(
        self,
        message: str,
        buttons: list
    ) -> None:
        """Send message with buttons to admin."""
        if not self._client:
            return
        
        try:
            await self._client.send_message(
                self._admin_user_id,
                message,
                parse_mode="markdown",
                buttons=buttons,
            )
        except Exception as e:
            logger.error(f"Failed to send with buttons: {e}")
    
    async def _setup_bot_commands(self) -> None:
        """Set up bot commands menu."""
        from telethon.tl.functions.bots import SetBotCommandsRequest
        from telethon.tl.types import BotCommand
        
        commands = [
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="menu", description="Show menu"),
            BotCommand(command="status", description="Bot status"),
            BotCommand(command="help", description="Show help"),
        ]
        
        try:
            await self._client(SetBotCommandsRequest(
                scope=None,
                lang_code="en",
                commands=commands
            ))
            logger.info("✅ Bot commands menu set up")
        except Exception as e:
            logger.warning(f"Failed to set bot commands: {e}")


# ==================== Factory Function ====================

async def create_bot(settings: "Settings") -> YourBot:
    """
    Create and initialize a bot instance.
    
    Args:
        settings: Application settings
    
    Returns:
        Initialized bot instance
    """
    bot = YourBot(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        bot_token=settings.telegram_bot_token,
        settings=settings,
        admin_user_id=settings.telegram_admin_user_id,
        notification_channel=settings.notification_channel,
    )
    
    await bot.start()
    return bot
```

---

## Testing Telegram Bots

### 1. Mock Telegram Client

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from telethon import TelegramClient

@pytest.fixture
def mock_telegram_client():
    """Create a mocked Telegram client."""
    client = AsyncMock(spec=TelegramClient)
    
    # Mock common methods
    client.start = AsyncMock()
    client.disconnect = AsyncMock()
    client.send_message = AsyncMock(return_value=MagicMock(id=1))
    client.get_me = AsyncMock(return_value=MagicMock(
        id=12345,
        username="test_bot",
        first_name="Test Bot"
    ))
    client.is_connected = MagicMock(return_value=True)
    
    return client
```

### 2. Test Command Handlers

```python
# tests/test_your_bot.py
import pytest
from unittest.mock import AsyncMock, patch
from src.your_bot import YourBot

@pytest.mark.asyncio
async def test_cmd_start(mock_telegram_client):
    """Test /start command."""
    settings = MagicMock()
    
    bot = YourBot(
        api_id=12345,
        api_hash="test_hash",
        bot_token="test_token",
        settings=settings,
        admin_user_id=67890,
    )
    bot._client = mock_telegram_client
    bot._initialized = True
    
    # Execute command
    await bot._cmd_start("")
    
    # Verify message sent
    mock_telegram_client.send_message.assert_called_once()
    call_args = mock_telegram_client.send_message.call_args
    assert "Welcome" in call_args[0][1]

@pytest.mark.asyncio
async def test_command_routing(mock_telegram_client):
    """Test command routing."""
    settings = MagicMock()
    
    bot = YourBot(
        api_id=12345,
        api_hash="test_hash",
        bot_token="test_token",
        settings=settings,
        admin_user_id=67890,
    )
    bot._client = mock_telegram_client
    bot._initialized = True
    
    # Mock command handler
    bot._cmd_status = AsyncMock()
    
    # Route command
    await bot._handle_command("/status")
    
    # Verify handler called
    bot._cmd_status.assert_called_once_with("")

@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting."""
    bot = YourBot(...)
    bot._rate_limit_seconds = 1.0
    
    user_id = 12345
    
    # First call should pass
    assert await bot._check_rate_limit(user_id) is True
    
    # Immediate second call should fail
    assert await bot._check_rate_limit(user_id) is False
    
    # After delay should pass
    await asyncio.sleep(1.1)
    assert await bot._check_rate_limit(user_id) is True
```

---

## Quick Reference

### Common Patterns

| Pattern | Use Case | Example |
|---------|----------|---------|
| Command Handler | User commands | `/start`, `/status` |
| Callback Handler | Button clicks | `Button.inline("Click", b"data")` |
| Stateful Input | Multi-step interactions | Wallet setup, confirmations |
| Interactive Menu | Navigation | Button-based menus |
| Notification | One-way messages | Trade alerts, errors |
| Rate Limiting | Prevent spam | 1 command per second |
| Authorization | Access control | Admin-only commands |

### Message Formatting

| Style | Markdown | Example |
|-------|----------|---------|
| Bold | `*text*` | `*Important*` |
| Italic | `_text_` | `_Note:_` |
| Code | `` `text` `` | `` `address` `` |
| Link | `[text](url)` | `[$TOKEN](https://t.me/...)` |
| Emoji | Direct | `🤖 Bot Started` |

### Button Layouts

```python
# Single row
[[Button.inline("Button 1", b"data1")]]

# Two columns
[[
    Button.inline("Left", b"left"),
    Button.inline("Right", b"right"),
]]

# Mixed layout
[
    [Button.inline("Full Width", b"fw")],
    [
        Button.inline("Half 1", b"h1"),
        Button.inline("Half 2", b"h2"),
    ],
]
```

---

## Best Practices

1. **Always use async/await** for all I/O operations
2. **Handle errors gracefully** - never let exceptions crash the bot
3. **Validate user input** before processing
4. **Use markdown formatting** for better readability
5. **Log everything** - use structured logging
6. **Rate limit commands** to prevent abuse
7. **Persist state** to survive restarts
8. **Send confirmation messages** for destructive actions
9. **Use buttons for common actions** - better UX than commands
10. **Test with mocks** - don't spam real Telegram in tests

---

*Last Updated: February 2026*
