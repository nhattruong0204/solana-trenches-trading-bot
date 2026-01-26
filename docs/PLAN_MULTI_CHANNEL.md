# Multi-Channel Signal Monitoring Implementation Plan

## Overview

Extend the existing bot to monitor multiple Telegram signal channels with distinct parsers per channel, while maintaining separate performance analytics for each.

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         TradingBot                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    ChannelRegistry                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │   │
│  │  │ VOLUME + SM  │  │    MAIN      │  │   Future     │      │   │
│  │  │  Channel     │  │   Channel    │  │   Channel    │      │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │   │
│  └─────────┼─────────────────┼─────────────────┼───────────────┘   │
│            │                 │                 │                    │
│  ┌─────────▼─────────────────▼─────────────────▼───────────────┐   │
│  │                    ParserRegistry                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │   │
│  │  │VolSmParsers  │  │ MainParsers  │  │ GenericParser│      │   │
│  │  │ - BuySignal  │  │ - BuySignal  │  │              │      │   │
│  │  │ - ProfitAlert│  │ - ProfitAlert│  │              │      │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

## Implementation Steps

### Step 1: Add Channel Registry (`src/constants.py` + `src/config.py`)

Add channel configuration dataclass and registry:

```python
# constants.py additions
TRENCHES_MAIN_CHANNEL_USERNAME = "fttrenches"
TRENCHES_MAIN_CHANNEL_NAME = "From The Trenches - MAIN"

# Channel identifiers (used as keys)
CHANNEL_VOLSM = "volsm"
CHANNEL_MAIN = "main"

# MAIN channel signal patterns (to be refined)
MAIN_BUY_SIGNAL_INDICATORS = (
    "🔥",  # TODO: Analyze actual MAIN channel message format
)
```

```python
# config.py additions
class MonitoredChannelConfig(BaseModel):
    """Configuration for a single monitored channel."""
    channel_id: str  # Unique identifier (e.g., "volsm", "main")
    username: str    # Telegram username (e.g., "fttrenches_volsm")
    display_name: str
    enabled: bool = True
    trading_enabled: bool = True
    commercial_mirroring: bool = False  # Only VOLSM mirrors to Premium
```

### Step 2: Create Parser Registry (`src/parsers.py`)

Add parser factory and registry pattern:

```python
class ParserRegistry:
    """Maps channel IDs to their corresponding parsers."""
    
    def __init__(self) -> None:
        self._parsers: dict[str, list[SignalParser]] = {}
        self._register_defaults()
    
    def _register_defaults(self) -> None:
        # VOLUME + SM channel parsers
        self._parsers[CHANNEL_VOLSM] = [
            BuySignalParser(),
            ProfitAlertParser(),
        ]
        # MAIN channel parsers (different patterns)
        self._parsers[CHANNEL_MAIN] = [
            MainChannelBuySignalParser(),
            MainChannelProfitAlertParser(),
        ]
    
    def get_parsers(self, channel_id: str) -> list[SignalParser]:
        return self._parsers.get(channel_id, [])
```

### Step 3: Update `TradingBot` (`src/bot.py`)

Changes required:
1. Initialize multiple channel entities
2. Single event handler for all channels
3. Route messages to correct parser based on channel
4. Pass `channel_id` to downstream processing

```python
# Key changes in bot.py
async def _init_channels(self) -> dict[str, Channel]:
    """Initialize all monitored channel entities."""
    entities = {}
    for channel_config in self._settings.monitored_channels:
        if channel_config.enabled:
            entity = await self._client.get_entity(channel_config.username)
            entities[channel_config.channel_id] = entity
    return entities

async def _on_new_message(self, event) -> None:
    # Identify which channel
    channel_id = self._get_channel_id(event.chat_id)
    
    # Get appropriate parsers
    parsers = self._parser_registry.get_parsers(channel_id)
    
    # Only mirror VOLSM to commercial channels
    if channel_id == CHANNEL_VOLSM:
        await self._mirror_to_commercial(...)
```

### Step 4: Parameterize Signal Database (`src/signal_database.py`)

Changes required:
1. Remove hardcoded `SIGNAL_CHANNEL_CHAT_TITLE`
2. Add `channel_id` parameter to query methods
3. Update stats to support filtering by channel

```python
# Add channel filtering to queries
async def get_signals_with_max_multipliers(
    self,
    hours: int = 24,
    limit: int = 100,
    channel_id: Optional[str] = None,  # NEW: filter by channel
) -> list[tuple[...]]
```

### Step 5: Update Admin Commands (`src/notification_bot.py`)

Add channel filtering to PnL commands:

```
/signalpnl 24h channel:volsm   - VOLUME + SM stats only
/signalpnl 7d channel:main     - MAIN channel stats only
/signalpnl 24h                 - Combined stats (default)
/channels                      - List monitored channels + status
```

### Step 6: Update Models (`src/models.py`)

Add channel tracking to signal models:

```python
@dataclass
class BuySignal:
    # ... existing fields ...
    channel_id: str = ""      # NEW: which channel this came from
    channel_name: str = ""    # NEW: display name
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/constants.py` | Add MAIN channel constants, channel IDs |
| `src/config.py` | Add `MonitoredChannelConfig`, channel list setting |
| `src/parsers.py` | Add `ParserRegistry`, MAIN channel parsers |
| `src/bot.py` | Multi-channel init, message routing |
| `src/signal_database.py` | Parameterize by channel_id |
| `src/notification_bot.py` | Channel filtering in commands |
| `src/models.py` | Add channel_id/channel_name fields |

## Open Questions

1. **MAIN channel message format**: Need sample messages to create accurate parsers
2. **Commercial mirroring scope**: Confirm only VOLSM → Premium (not MAIN)
3. **Default PnL view**: Combined or require channel specification?

## Testing Strategy

1. Unit tests for new parsers
2. Unit tests for ParserRegistry
3. Integration test for multi-channel message routing
4. Manual testing with live MAIN channel messages

## Rollout Plan

1. Phase 1: Add infrastructure (registry, config) without breaking existing
2. Phase 2: Add MAIN channel monitoring in "observe only" mode
3. Phase 3: Enable MAIN channel in database/stats
4. Phase 4: Production deployment with both channels active
