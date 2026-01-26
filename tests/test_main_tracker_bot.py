"""
Tests for main_tracker_bot.py

Regression tests for bugs fixed in the MAIN channel tracker bot.
"""

from __future__ import annotations

import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBootstrapSignalsParameterName:
    """
    Regression test for the bootstrap_completed -> mark_bootstrap_complete bug.

    Bug: _cmd_bootstrap_signals was calling update_channel_cursor with
    'bootstrap_completed=True' instead of 'mark_bootstrap_complete=True'.

    This caused a TypeError because the parameter name didn't match the
    function signature in signal_database.py.

    Fixed in: feature/handle-new-main-channel branch
    """

    def test_bootstrap_uses_correct_parameter_name(self):
        """
        Verify that _cmd_bootstrap_signals uses 'mark_bootstrap_complete'
        parameter name, not 'bootstrap_completed'.
        """
        from src.main_tracker_bot import MainTrackerBot

        # Get the source code of _cmd_bootstrap_signals method
        source = inspect.getsource(MainTrackerBot._cmd_bootstrap_signals)

        # The method should use mark_bootstrap_complete=True
        assert "mark_bootstrap_complete=True" in source, (
            "_cmd_bootstrap_signals must use 'mark_bootstrap_complete=True' "
            "when calling update_channel_cursor, not 'bootstrap_completed=True'"
        )

        # The method should NOT use the incorrect parameter name
        assert "bootstrap_completed=True" not in source, (
            "_cmd_bootstrap_signals should NOT use 'bootstrap_completed=True' - "
            "the correct parameter name is 'mark_bootstrap_complete=True'"
        )

    def test_update_channel_cursor_signature(self):
        """
        Verify that update_channel_cursor has the expected parameter name.
        """
        from src.signal_database import SignalDatabase

        # Check the signature of update_channel_cursor
        sig = inspect.signature(SignalDatabase.update_channel_cursor)
        params = list(sig.parameters.keys())

        # Should have 'mark_bootstrap_complete' parameter
        assert "mark_bootstrap_complete" in params, (
            "update_channel_cursor should have 'mark_bootstrap_complete' parameter"
        )

        # Should NOT have 'bootstrap_completed' parameter
        assert "bootstrap_completed" not in params, (
            "update_channel_cursor should NOT have 'bootstrap_completed' parameter"
        )


class TestSessionFileConfiguration:
    """
    Regression tests for session file configuration.

    Bug: Both trading-bot and main-tracker could use the same Telegram session
    file, causing SQLite "database is locked" errors during concurrent operations.

    Fixed in: feature/handle-new-main-channel branch
    """

    def test_main_tracker_env_variables_documented(self):
        """
        Verify that .env.example documents separate session for main-tracker.
        """
        import os
        from pathlib import Path

        env_example_path = Path(__file__).parent.parent / ".env.example"

        if env_example_path.exists():
            content = env_example_path.read_text()

            # Should mention using different session file
            assert "MAIN_SESSION_FILE" in content, (
                ".env.example should document MAIN_SESSION_FILE variable"
            )

            # Should warn about not using same session as trading-bot
            assert "different" in content.lower() or "dedicated" in content.lower() or "separate" in content.lower(), (
                ".env.example should warn about using different session file than trading-bot"
            )

    def test_docker_compose_uses_dedicated_session_for_main_tracker(self):
        """
        Verify that docker-compose.yml configures a dedicated session file for main-tracker.
        """
        import yaml
        from pathlib import Path

        docker_compose_path = Path(__file__).parent.parent / "docker-compose.yml"

        if docker_compose_path.exists():
            content = yaml.safe_load(docker_compose_path.read_text())

            # Get main-tracker service config
            main_tracker = content.get("services", {}).get("main-tracker", {})
            env_list = main_tracker.get("environment", [])

            # Convert list of "KEY=VALUE" strings to dict
            env_dict = {}
            for item in env_list:
                if "=" in item:
                    key, value = item.split("=", 1)
                    env_dict[key.strip("- ")] = value

            # Check that MAIN_SESSION_FILE or SESSION_FILE is configured
            session_file = env_dict.get("MAIN_SESSION_FILE") or env_dict.get("SESSION_FILE")

            assert session_file is not None, (
                "main-tracker service should have MAIN_SESSION_FILE or SESSION_FILE configured"
            )

            # Should NOT use same file as trading-bot (wallet_tracker_session)
            assert "wallet_tracker" not in session_file.lower(), (
                "main-tracker should NOT use wallet_tracker_session to avoid conflicts"
            )


class TestMainTrackerBot:
    """Basic tests for MainTrackerBot initialization."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        return settings

    def test_main_tracker_bot_can_be_imported(self):
        """Test that MainTrackerBot can be imported."""
        from src.main_tracker_bot import MainTrackerBot
        assert MainTrackerBot is not None

    def test_main_tracker_bot_has_required_methods(self):
        """Test that MainTrackerBot has all required command methods."""
        from src.main_tracker_bot import MainTrackerBot

        required_methods = [
            "_cmd_start",
            "_cmd_menu",
            "_cmd_help",
            "_cmd_sync_signals",
            "_cmd_bootstrap_signals",
            "_cmd_signal_pnl",
            "_cmd_real_pnl",
        ]

        for method_name in required_methods:
            assert hasattr(MainTrackerBot, method_name), (
                f"MainTrackerBot should have {method_name} method"
            )
