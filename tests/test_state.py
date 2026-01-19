"""
Tests for the state management module.
"""

import pytest
import json
from datetime import datetime, timezone
from pathlib import Path

from src.state import TradingState
from src.models import Position, PositionStatus
from src.exceptions import (
    DuplicatePositionError,
    MaxPositionsReachedError,
    PositionNotFoundError,
)


class TestTradingState:
    """Tests for TradingState."""
    
    @pytest.fixture
    def state(self, tmp_state_file):
        """Create a fresh trading state for each test."""
        return TradingState(tmp_state_file)
    
    @pytest.mark.asyncio
    async def test_add_position(self, state, sample_position):
        """Test adding a new position."""
        await state.add_position(sample_position)
        
        assert state.has_position(sample_position.token_address)
        assert state.open_position_count == 1
    
    @pytest.mark.asyncio
    async def test_add_duplicate_position_raises(self, state, sample_position):
        """Test that adding duplicate position raises error."""
        await state.add_position(sample_position)
        
        with pytest.raises(DuplicatePositionError):
            await state.add_position(sample_position)
    
    @pytest.mark.asyncio
    async def test_max_positions_limit(self, state):
        """Test that max positions limit is enforced."""
        # Add 5 positions
        for i in range(5):
            pos = Position(
                token_address=f"address{i:040d}",
                token_symbol=f"TOKEN{i}",
                buy_time=datetime.now(timezone.utc),
                buy_amount_sol=0.1,
                signal_msg_id=i,
            )
            await state.add_position(pos, max_positions=5)
        
        # Try to add one more
        new_pos = Position(
            token_address="newaddress00000000000000000000000000000",
            token_symbol="NEW",
            buy_time=datetime.now(timezone.utc),
            buy_amount_sol=0.1,
            signal_msg_id=100,
        )
        
        with pytest.raises(MaxPositionsReachedError):
            await state.add_position(new_pos, max_positions=5)
    
    @pytest.mark.asyncio
    async def test_get_position_by_signal(self, state, sample_position):
        """Test getting position by signal message ID."""
        await state.add_position(sample_position)
        
        found = state.get_position_by_signal(sample_position.signal_msg_id)
        assert found is not None
        assert found.token_address == sample_position.token_address
        
        not_found = state.get_position_by_signal(99999)
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_mark_partial_sell(self, state, sample_position):
        """Test marking position as partially sold."""
        await state.add_position(sample_position)
        
        updated = await state.mark_partial_sell(
            sample_position.token_address,
            percentage=50.0,
            multiplier=2.0,
        )
        
        assert updated.status == PositionStatus.PARTIAL_SOLD
        assert updated.sold_percentage == 50.0
        assert updated.last_multiplier == 2.0
    
    @pytest.mark.asyncio
    async def test_mark_partial_sell_not_found(self, state):
        """Test that marking non-existent position raises error."""
        with pytest.raises(PositionNotFoundError):
            await state.mark_partial_sell("nonexistent", 50.0, 2.0)
    
    @pytest.mark.asyncio
    async def test_close_position(self, state, sample_position):
        """Test closing a position."""
        await state.add_position(sample_position)
        
        closed = await state.close_position(sample_position.token_address, multiplier=3.0)
        
        assert closed.status == PositionStatus.CLOSED
        assert closed.sold_percentage == 100.0
    
    def test_save_and_load(self, state, sample_position, tmp_state_file):
        """Test state persistence."""
        import asyncio
        
        # Add position and save
        asyncio.run(state.add_position(sample_position))
        state.save()
        
        # Create new state and load
        new_state = TradingState(tmp_state_file)
        loaded = new_state.load()
        
        assert loaded is True
        assert new_state.has_position(sample_position.token_address)
        assert new_state.open_position_count == 1
    
    def test_load_nonexistent_file(self, tmp_path):
        """Test loading from nonexistent file."""
        state = TradingState(tmp_path / "nonexistent.json")
        loaded = state.load()
        
        assert loaded is False
        assert state.open_position_count == 0
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, state, sample_position):
        """Test getting trading statistics."""
        await state.add_position(sample_position)
        
        stats = state.get_statistics()
        
        assert stats["total_positions"] == 1
        assert stats["open_positions"] == 1
        assert stats["partial_positions"] == 0
        assert stats["closed_positions"] == 0
        assert stats["total_invested_sol"] == 0.1
    
    @pytest.mark.asyncio
    async def test_open_positions_property(self, state):
        """Test the open_positions property."""
        # Add open position
        pos1 = Position(
            token_address="address10000000000000000000000000000000",
            token_symbol="OPEN",
            buy_time=datetime.now(timezone.utc),
            buy_amount_sol=0.1,
            signal_msg_id=1,
            status=PositionStatus.OPEN,
        )
        
        # Add closed position
        pos2 = Position(
            token_address="address20000000000000000000000000000000",
            token_symbol="CLOSED",
            buy_time=datetime.now(timezone.utc),
            buy_amount_sol=0.1,
            signal_msg_id=2,
            status=PositionStatus.CLOSED,
        )
        
        await state.add_position(pos1)
        # Manually add closed position to bypass checks
        state._positions[pos2.token_address] = pos2
        
        open_positions = state.open_positions
        
        assert len(open_positions) == 1
        assert "address10000000000000000000000000000000" in open_positions
        assert "address20000000000000000000000000000000" not in open_positions
