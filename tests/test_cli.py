"""
Tests for the cli module.

Tests command-line argument parsing, validation, and configuration.
"""

import pytest
import argparse
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.cli import create_parser


class TestCreateParser:
    """Tests for create_parser function."""
    
    def test_parser_creation(self):
        """Test that parser is created successfully."""
        parser = create_parser()
        
        assert parser is not None
        assert isinstance(parser, argparse.ArgumentParser)
    
    def test_parser_prog_name(self):
        """Test parser program name."""
        parser = create_parser()
        
        assert parser.prog == "trading-bot"
    
    def test_parser_description(self):
        """Test parser has description."""
        parser = create_parser()
        
        assert "Solana Auto Trading Bot" in parser.description


class TestVersionArgument:
    """Tests for version argument."""
    
    def test_version_short(self):
        """Test -V version flag."""
        parser = create_parser()
        
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["-V"])
        
        assert exc.value.code == 0
    
    def test_version_long(self):
        """Test --version flag."""
        parser = create_parser()
        
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--version"])
        
        assert exc.value.code == 0


class TestLoggingArguments:
    """Tests for logging arguments."""
    
    def test_verbose_short(self):
        """Test -v verbose flag."""
        parser = create_parser()
        args = parser.parse_args(["-v"])
        
        assert args.verbose is True
    
    def test_verbose_long(self):
        """Test --verbose flag."""
        parser = create_parser()
        args = parser.parse_args(["--verbose"])
        
        assert args.verbose is True
    
    def test_quiet_short(self):
        """Test -q quiet flag."""
        parser = create_parser()
        args = parser.parse_args(["-q"])
        
        assert args.quiet is True
    
    def test_quiet_long(self):
        """Test --quiet flag."""
        parser = create_parser()
        args = parser.parse_args(["--quiet"])
        
        assert args.quiet is True
    
    def test_log_file(self):
        """Test --log-file argument."""
        parser = create_parser()
        args = parser.parse_args(["--log-file", "/tmp/test.log"])
        
        assert args.log_file == Path("/tmp/test.log")
    
    def test_default_verbose(self):
        """Test default verbose is False."""
        parser = create_parser()
        args = parser.parse_args([])
        
        assert args.verbose is False
    
    def test_default_quiet(self):
        """Test default quiet is False."""
        parser = create_parser()
        args = parser.parse_args([])
        
        assert args.quiet is False


class TestTradingArguments:
    """Tests for trading arguments."""
    
    def test_live_flag(self):
        """Test --live flag."""
        parser = create_parser()
        args = parser.parse_args(["--live"])
        
        assert args.live is True
    
    def test_dry_run_flag(self):
        """Test --dry-run flag."""
        parser = create_parser()
        args = parser.parse_args(["--dry-run"])
        
        assert args.dry_run is True
    
    def test_dry_run_default(self):
        """Test default dry-run is True."""
        parser = create_parser()
        args = parser.parse_args([])
        
        assert args.dry_run is True
    
    def test_buy_amount(self):
        """Test --buy-amount argument."""
        parser = create_parser()
        args = parser.parse_args(["--buy-amount", "0.5"])
        
        assert args.buy_amount == 0.5
    
    def test_buy_amount_decimal(self):
        """Test --buy-amount with decimal."""
        parser = create_parser()
        args = parser.parse_args(["--buy-amount", "0.123"])
        
        assert args.buy_amount == 0.123
    
    def test_sell_percentage(self):
        """Test --sell-percentage argument."""
        parser = create_parser()
        args = parser.parse_args(["--sell-percentage", "50"])
        
        assert args.sell_percentage == 50
    
    def test_sell_percentage_invalid_low(self):
        """Test --sell-percentage with value below 1."""
        parser = create_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args(["--sell-percentage", "0"])
    
    def test_sell_percentage_invalid_high(self):
        """Test --sell-percentage with value above 100."""
        parser = create_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args(["--sell-percentage", "101"])
    
    def test_min_multiplier(self):
        """Test --min-multiplier argument."""
        parser = create_parser()
        args = parser.parse_args(["--min-multiplier", "2.0"])
        
        assert args.min_multiplier == 2.0
    
    def test_max_positions(self):
        """Test --max-positions argument."""
        parser = create_parser()
        args = parser.parse_args(["--max-positions", "5"])
        
        assert args.max_positions == 5
    
    def test_disabled_flag(self):
        """Test --disabled flag."""
        parser = create_parser()
        args = parser.parse_args(["--disabled"])
        
        assert args.disabled is True


class TestStateArguments:
    """Tests for state management arguments."""
    
    def test_state_file(self):
        """Test --state-file argument."""
        parser = create_parser()
        args = parser.parse_args(["--state-file", "/tmp/state.json"])
        
        assert args.state_file == Path("/tmp/state.json")
    
    def test_reset_state(self):
        """Test --reset-state flag."""
        parser = create_parser()
        args = parser.parse_args(["--reset-state"])
        
        assert args.reset_state is True


class TestSubcommands:
    """Tests for subcommands."""
    
    def test_status_command(self):
        """Test status subcommand."""
        parser = create_parser()
        args = parser.parse_args(["status"])
        
        assert args.command == "status"
    
    def test_validate_command(self):
        """Test validate subcommand."""
        parser = create_parser()
        args = parser.parse_args(["validate"])
        
        assert args.command == "validate"
    
    def test_no_command(self):
        """Test no subcommand specified."""
        parser = create_parser()
        args = parser.parse_args([])
        
        assert args.command is None


class TestCombinedArguments:
    """Tests for combining multiple arguments."""
    
    def test_live_with_buy_amount(self):
        """Test --live with --buy-amount."""
        parser = create_parser()
        args = parser.parse_args(["--live", "--buy-amount", "1.0"])
        
        assert args.live is True
        assert args.buy_amount == 1.0
    
    def test_verbose_with_log_file(self):
        """Test --verbose with --log-file."""
        parser = create_parser()
        args = parser.parse_args(["--verbose", "--log-file", "/tmp/debug.log"])
        
        assert args.verbose is True
        assert args.log_file == Path("/tmp/debug.log")
    
    def test_all_trading_options(self):
        """Test all trading options together."""
        parser = create_parser()
        args = parser.parse_args([
            "--live",
            "--buy-amount", "0.5",
            "--sell-percentage", "75",
            "--min-multiplier", "2.5",
            "--max-positions", "10",
        ])
        
        assert args.live is True
        assert args.buy_amount == 0.5
        assert args.sell_percentage == 75
        assert args.min_multiplier == 2.5
        assert args.max_positions == 10


class TestInvalidArguments:
    """Tests for invalid arguments."""
    
    def test_invalid_buy_amount_type(self):
        """Test --buy-amount with non-numeric value."""
        parser = create_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args(["--buy-amount", "abc"])
    
    def test_invalid_max_positions_type(self):
        """Test --max-positions with non-integer."""
        parser = create_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args(["--max-positions", "5.5"])
    
    def test_unknown_argument(self):
        """Test unknown argument."""
        parser = create_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args(["--unknown-flag"])


class TestHelpText:
    """Tests for help text availability."""
    
    def test_help_exits(self):
        """Test -h flag exits cleanly."""
        parser = create_parser()
        
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["-h"])
        
        assert exc.value.code == 0
    
    def test_help_long_exits(self):
        """Test --help flag exits cleanly."""
        parser = create_parser()
        
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--help"])
        
        assert exc.value.code == 0
