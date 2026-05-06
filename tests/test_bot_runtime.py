from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
root_str = str(ROOT)

if root_str not in sys.path:
    sys.path.insert(0, root_str)

from orca_bot import bot as bot_module
from orca_bot.bot import (
    _build_console_status,
    _configure_logger,
    _get_restart_args,
    _resolve_runtime_credentials,
)


class RuntimeCredentialTests(unittest.TestCase):
    def test_prefers_dev_token_when_available(self) -> None:
        with patch.dict(
            os.environ,
            {"DISCORD_TOKEN": "prod-token", "BOT_TOKEN_DEV": "dev-token"},
            clear=True,
        ):
            self.assertEqual(_resolve_runtime_credentials(), ("dev", "dev-token"))

    def test_respects_default_profile_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DISCORD_TOKEN": "prod-token",
                "BOT_TOKEN_DEV": "dev-token",
                "ORCA_PROFILE": "default",
            },
            clear=True,
        ):
            self.assertEqual(_resolve_runtime_credentials(), ("default", "prod-token"))

    def test_errors_when_dev_profile_is_requested_without_dev_token(self) -> None:
        with patch.dict(
            os.environ,
            {"DISCORD_TOKEN": "prod-token", "ORCA_PROFILE": "dev"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "BOT_TOKEN_DEV is missing"):
                _resolve_runtime_credentials()

    def test_uses_default_token_when_only_prod_token_is_set(self) -> None:
        with patch.dict(
            os.environ,
            {"DISCORD_TOKEN": "prod-token"},
            clear=True,
        ):
            self.assertEqual(_resolve_runtime_credentials(), ("default", "prod-token"))

    def test_errors_when_default_profile_is_requested_without_discord_token(self) -> None:
        with patch.dict(
            os.environ,
            {"BOT_TOKEN_DEV": "dev-token", "ORCA_PROFILE": "default"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "DISCORD_TOKEN is missing"):
                _resolve_runtime_credentials()

    def test_errors_when_profile_is_invalid(self) -> None:
        with patch.dict(
            os.environ,
            {"DISCORD_TOKEN": "prod-token", "ORCA_PROFILE": "staging"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "Invalid ORCA_PROFILE"):
                _resolve_runtime_credentials()

    def test_errors_when_no_tokens_are_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Missing DISCORD_TOKEN"):
                _resolve_runtime_credentials()


class LoggerConfigTests(unittest.TestCase):
    def test_configures_orca_bot_package_logger(self) -> None:
        logger = _configure_logger()
        self.assertEqual(logger.name, "orca_bot")

    def test_logger_does_not_propagate_to_root(self) -> None:
        logger = _configure_logger()
        self.assertFalse(logger.propagate)

    def test_logger_has_handlers_attached(self) -> None:
        logger = _configure_logger()
        self.assertGreater(len(logger.handlers), 0)

    def test_cog_loggers_reach_orca_bot_handlers(self) -> None:
        cog_logger = logging.getLogger("orca_bot.cogs.music")
        package_logger = logging.getLogger("orca_bot")
        self.assertTrue(cog_logger.propagate)
        self.assertGreater(len(package_logger.handlers), 0)


class RestartArgsTests(unittest.TestCase):
    def test_uses_orig_argv_when_available(self) -> None:
        with patch.object(
            sys, "orig_argv", ["/usr/bin/python", "-m", "orca_bot"], create=True
        ):
            with patch("sys.executable", "/usr/bin/python"):
                result = _get_restart_args()
        self.assertEqual(result, ["/usr/bin/python", "-m", "orca_bot"])

    def test_falls_back_to_sys_argv_when_orig_argv_is_absent(self) -> None:
        with patch.object(sys, "orig_argv", None, create=True):
            with patch("sys.executable", "/usr/bin/python"):
                with patch("sys.argv", ["run_bot.py"]):
                    result = _get_restart_args()
        self.assertEqual(result, ["/usr/bin/python", "run_bot.py"])


class ConsoleStatusTests(unittest.TestCase):
    def _status(self, *, user_name: str | None, ready: bool, latency: float) -> str:
        mock_client = MagicMock()
        mock_client.user = MagicMock() if user_name else None
        if user_name:
            mock_client.user.name = user_name
        mock_client.is_ready.return_value = ready
        mock_client.is_closed.return_value = False
        mock_client.latency = latency
        mock_client.guilds = []
        mock_client.voice_clients = []
        with patch.object(bot_module, "client", mock_client):
            return _build_console_status("dev")

    def test_includes_profile_user_and_latency_when_ready(self) -> None:
        status = self._status(user_name="Orca", ready=True, latency=0.05)
        self.assertIn("Profile: dev", status)
        self.assertIn("Orca", status)
        self.assertIn("50 ms", status)

    def test_shows_not_logged_in_when_user_is_none(self) -> None:
        status = self._status(user_name=None, ready=False, latency=0.0)
        self.assertIn("Not logged in", status)

    def test_latency_shown_as_na_when_not_ready(self) -> None:
        status = self._status(user_name="Orca", ready=False, latency=0.0)
        self.assertIn("n/a", status)


if __name__ == "__main__":
    unittest.main()
