# Copilot Quick Start: Building Telegram Bots

> **For Copilot Agents**: This guide helps you quickly understand and replicate the Telegram bot patterns used in this repository.

---

## 🎯 What This Repository Does

This repo implements **3 types of Telegram bots**:

1. **NotificationBot** (`src/notification_bot.py`) - Full-featured admin bot with 30+ commands
2. **TelegramController** (`src/controller.py`) - Simplified remote control interface
3. **CommercialBot** (`src/commercial_bot.py`) - Premium features wrapper

---

## 📚 Key Resources

**MUST READ FIRST:**
- `/docs/ARCHITECTURE.md` - System architecture and component responsibilities
- `/docs/CONVENTIONS.md` - Code style, patterns, and conventions
- `/docs/TELEGRAM_BOT_GUIDE.md` - Comprehensive Telegram bot patterns

**Reference Implementations:**
- `src/notification_bot.py` - Main bot with all features (3238 lines)
- `src/controller.py` - Simpler controller pattern (733 lines)

---

## 🔧 Tech Stack

```python
# Core library
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.custom import Button

# Bot token from BotFather
bot_token = "YOUR_BOT_TOKEN"
```

---

## 🚀 Quick Implementation Pattern

### 1. Minimal Bot Structure

```python
"""Your bot module docstring."""
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.custom import Button
import logging

logger = logging.getLogger(__name__)

class YourBot:
    """Bot description and commands list."""
    
    def __init__(self, api_id: int, api_hash: str, bot_token: str, 
                 admin_user_id: int):
        self._api_id = api_id
        self._api_hash = api_hash
        self._bot_token = bot_token
        self._admin_user_id = admin_user_id
        self._client = None
        self._initialized = False
    
    async def start(self):
        """Initialize bot."""
        self._client = TelegramClient(StringSession(), 
                                       self._api_id, self._api_hash)
        await self._client.start(bot_token=self._bot_token)
        self._register_handlers()
        self._initialized = True
        logger.info("✅ Bot started")
    
    def _register_handlers(self):
        """Register event handlers."""
        @self._client.on(events.NewMessage(chats=[self._admin_user_id]))
        async def handle_message(event):
            await self._handle_message(event)
        
        @self._client.on(events.CallbackQuery)
        async def handle_callback(event):
            await self._handle_callback(event)
    
    async def _handle_message(self, event):
        """Route messages."""
        text = event.message.text.strip()
        if text.startswith("/"):
            await self._handle_command(text)
    
    async def _handle_command(self, text: str):
        """Route commands to handlers."""
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        handlers = {
            "/start": self._cmd_start,
            "/menu": self._cmd_menu,
            "/help": self._cmd_help,
        }
        
        handler = handlers.get(command)
        if handler:
            await handler(args)
    
    async def _handle_callback(self, event):
        """Handle button clicks."""
        data = event.data.decode('utf-8')
        await event.answer()  # Always acknowledge
        # Route to handlers based on data
    
    async def _cmd_start(self, args: str):
        """Handle /start."""
        await self._send_to_admin("🤖 Bot started! Use /menu")
    
    async def _cmd_menu(self, args: str):
        """Show menu with buttons."""
        message = "Select an option:"
        buttons = [
            [Button.inline("📊 Status", b"cmd_status")],
            [Button.inline("❓ Help", b"cmd_help")],
        ]
        await self._send_to_admin_with_buttons(message, buttons)
    
    async def _cmd_help(self, args: str):
        """Show help."""
        await self._send_to_admin(
            "📚 Commands:\n/start - Start\n/menu - Menu\n/help - Help"
        )
    
    async def _send_to_admin(self, message: str):
        """Send message to admin."""
        await self._client.send_message(self._admin_user_id, message, 
                                         parse_mode="markdown")
    
    async def _send_to_admin_with_buttons(self, message: str, buttons: list):
        """Send message with buttons."""
        await self._client.send_message(self._admin_user_id, message,
                                         parse_mode="markdown", buttons=buttons)
    
    async def stop(self):
        """Cleanup."""
        if self._client:
            await self._client.disconnect()
```

---

## 💡 Common Patterns in This Repo

### Pattern 1: Command Handlers

```python
# In _handle_command method
handlers = {
    "/command": self._cmd_command,
}

# Command implementation
async def _cmd_command(self, args: str) -> None:
    """Handle /command."""
    if not args:
        await self._send_to_admin("❌ Missing argument")
        return
    
    try:
        # Process args
        value = float(args)
        # Do something
        await self._send_to_admin(f"✅ Updated to {value}")
    except ValueError:
        await self._send_to_admin("❌ Invalid input")
```

### Pattern 2: Interactive Buttons

```python
def _get_menu_buttons(self) -> list:
    """Generate button layout."""
    return [
        # Row 1: Two buttons
        [
            Button.inline("📊 Status", b"cmd_status"),
            Button.inline("⚙️ Settings", b"cmd_settings"),
        ],
        # Row 2: One button
        [Button.inline("❓ Help", b"cmd_help")],
    ]

async def _handle_callback(self, event):
    """Handle button clicks."""
    data = event.data.decode('utf-8')
    await event.answer()  # ALWAYS acknowledge
    
    if data == "cmd_status":
        await self._cmd_status("")
    elif data == "cmd_settings":
        await self._cmd_settings("")
```

### Pattern 3: Stateful Input

```python
class YourBot:
    def __init__(self, ...):
        self._awaiting_wallet = False
    
    async def _cmd_setwallet(self, args: str):
        """Initiate wallet input."""
        await self._send_to_admin("Please send your wallet address:")
        self._awaiting_wallet = True
    
    async def _handle_message(self, event):
        """Check for stateful input first."""
        text = event.message.text.strip()
        
        if self._awaiting_wallet:
            await self._handle_wallet_input(text)
            return
        
        # Normal processing...
    
    async def _handle_wallet_input(self, text: str):
        """Handle wallet input."""
        self._awaiting_wallet = False  # Reset state
        
        if self._is_valid_wallet(text):
            self._wallet = text
            await self._send_to_admin(f"✅ Wallet set to {text[:8]}...")
        else:
            await self._send_to_admin("❌ Invalid wallet address")
```

### Pattern 4: Notifications

```python
async def notify_event(self, event_data: dict):
    """Send structured notification."""
    message = (
        f"🔔 *Event Occurred*\n\n"
        f"Type: `{event_data['type']}`\n"
        f"Time: `{event_data['time']}`\n"
        f"Details: `{event_data['details']}`"
    )
    
    # Send to channel or admin
    target = self._channel_entity if self._channel_entity else self._admin_user_id
    await self._client.send_message(target, message, parse_mode="markdown")
```

---

## 🎨 Message Formatting

```python
# Use markdown formatting
message = (
    "*Bold text*\n"
    "_Italic text_\n"
    "`Code or monospace`\n"
    "[Link text](https://example.com)\n"
    "🤖 Emojis work directly\n"
)

await self._send_to_admin(message)
```

---

## 🔐 Authorization Pattern

```python
def _is_admin(self, user_id: int) -> bool:
    """Check if user is admin."""
    return user_id == self._admin_user_id

async def _handle_message(self, event):
    """Check authorization first."""
    sender = await event.get_sender()
    if not sender or not self._is_admin(sender.id):
        await event.respond("⚠️ Not authorized")
        return
    
    # Process message...
```

---

## 🛠️ Configuration Pattern

```python
from src.config import get_settings

settings = get_settings()

bot = YourBot(
    api_id=settings.telegram_api_id,
    api_hash=settings.telegram_api_hash,
    bot_token=settings.telegram_bot_token,
    admin_user_id=settings.telegram_admin_user_id,
)
```

---

## ⚠️ Error Handling Pattern

```python
async def _handle_command(self, text: str):
    """Handle commands with error recovery."""
    handler = self._handlers.get(command)
    
    try:
        await handler(args)
    except ValueError as e:
        await self._send_to_admin(f"❌ Invalid input: {e}")
    except Exception as e:
        logger.error(f"Error in {command}: {e}", exc_info=True)
        await self._send_to_admin(f"❌ Unexpected error")
```

---

## 📋 Checklist for New Bot

- [ ] Review `docs/ARCHITECTURE.md` for system context
- [ ] Review `docs/CONVENTIONS.md` for code style
- [ ] Choose reference implementation (NotificationBot or Controller)
- [ ] Create bot class with `__init__`, `start()`, `stop()`
- [ ] Implement `_register_handlers()` for events
- [ ] Create command routing in `_handle_command()`
- [ ] Implement each `_cmd_*()` method
- [ ] Add button handlers in `_handle_callback()`
- [ ] Test with admin user ID
- [ ] Add error handling and logging
- [ ] Document commands in class docstring

---

## 🔍 Where to Look for Examples

| Feature | File | Lines |
|---------|------|-------|
| Full bot with 30+ commands | `src/notification_bot.py` | 1-3238 |
| Simpler controller | `src/controller.py` | 1-733 |
| Premium features wrapper | `src/commercial_bot.py` | 1-697 |
| Button menu example | `notification_bot.py` | 883-933 |
| Command routing | `notification_bot.py` | 815-864 |
| Callback handling | `notification_bot.py` | 967-1024 |
| Stateful input | `notification_bot.py` | 743-813 |
| Authorization check | `notification_bot.py` | 698-710 |

---

## 🧪 Testing Pattern

```python
# tests/test_your_bot.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_telegram_client():
    client = AsyncMock()
    client.send_message = AsyncMock(return_value=MagicMock(id=1))
    return client

@pytest.mark.asyncio
async def test_cmd_start(mock_telegram_client):
    bot = YourBot(...)
    bot._client = mock_telegram_client
    
    await bot._cmd_start("")
    
    mock_telegram_client.send_message.assert_called_once()
```

---

## 🚨 Common Pitfalls

1. **Not acknowledging callbacks**: Always call `await event.answer()` in callback handlers
2. **Missing authorization checks**: Always verify user ID before processing
3. **Not handling errors**: Wrap command handlers in try-except
4. **Hardcoding values**: Use constants from `src/constants.py`
5. **Not using async**: All I/O must be async
6. **Missing markdown parse_mode**: Add `parse_mode="markdown"` to send_message
7. **Not removing @botname**: Strip `@botname` from commands

---

## 🎓 Learning Path

1. **Start**: Read `docs/ARCHITECTURE.md` (10 min)
2. **Understand**: Review `src/controller.py` - simpler example (15 min)
3. **Deep dive**: Study `src/notification_bot.py` - full features (30 min)
4. **Reference**: Use `docs/TELEGRAM_BOT_GUIDE.md` while coding (ongoing)
5. **Build**: Start with minimal bot, add features incrementally

---

## 📞 Key Functions Reference

```python
# Sending messages
await self._client.send_message(user_id, text, parse_mode="markdown")
await self._client.send_message(user_id, text, buttons=buttons)

# Handling events
@self._client.on(events.NewMessage(chats=[user_id]))
@self._client.on(events.CallbackQuery)

# Buttons
Button.inline(text="Click", data=b"callback_data")
Button.url(text="Link", url="https://...")

# Callback handling
await event.answer()  # Acknowledge
data = event.data.decode('utf-8')  # Get callback data

# Getting sender
sender = await event.get_sender()
user_id = sender.id
```

---

## 🎯 Success Criteria

Your bot should:
- ✅ Start without errors
- ✅ Respond to /start, /help, /menu
- ✅ Have at least one button menu
- ✅ Handle callbacks correctly
- ✅ Check authorization
- ✅ Handle errors gracefully
- ✅ Log important events
- ✅ Follow code conventions from `docs/CONVENTIONS.md`
- ✅ Match architecture patterns from `docs/ARCHITECTURE.md`

---

*For detailed patterns and complete examples, see `/docs/TELEGRAM_BOT_GUIDE.md`*
