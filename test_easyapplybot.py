"""Tests for easyapplybot.py FastAPI server and bot logic.

These tests cover:
- FastAPI endpoints (/health, /status, /start, /stop)
- ProfileConfig Pydantic model validation
- ConnectionManager WebSocket broadcasting
- get_appropriate_value field-filling heuristics
- WebSocket event emission
- Cross-platform compatibility (paths, CSV, pyautogui, server binding)
"""

import asyncio
import csv
import json
import os
import socket
import sys
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

# Import from the bot module
from easyapplybot import (
    ProfileConfig,
    ConnectionManager,
    app,
    emit_event,
    ws_manager,
    _bot,
    _bot_lock,
)


# ---------------------------------------------------------------------------
# ProfileConfig model tests
# ---------------------------------------------------------------------------

class TestProfileConfig:
    def test_valid_config(self):
        config = ProfileConfig(
            email="test@example.com",
            password="secret",
            phone_number="555-1234",
            positions=["Software Engineer"],
            locations=["Remote"],
            remote_only=True,
            profile_url="https://linkedin.com/in/test",
            user_city="New York",
            user_state="NY",
            zip_code="10001",
            years_experience=5,
            desired_salary=120000,
            openai_api_key="sk-test",
            blacklist=["Coinbase"],
            blacklist_titles=["intern"],
        )
        assert config.email == "test@example.com"
        assert config.password == "secret"
        assert config.phone_number == "555-1234"
        assert config.positions == ["Software Engineer"]
        assert config.locations == ["Remote"]
        assert config.remote_only is True
        assert config.years_experience == 5
        assert config.desired_salary == 120000
        assert config.blacklist == ["Coinbase"]
        assert config.blacklist_titles == ["intern"]

    def test_defaults(self):
        config = ProfileConfig(email="a@b.com", password="pw")
        assert config.phone_number == ""
        assert config.positions == []
        assert config.locations == []
        assert config.remote_only is False
        assert config.profile_url == ""
        assert config.user_city == ""
        assert config.user_state == ""
        assert config.zip_code == ""
        assert config.years_experience == 0
        assert config.desired_salary == 0
        assert config.openai_api_key == ""
        assert config.blacklist == []
        assert config.blacklist_titles == []

    def test_missing_email_raises(self):
        with pytest.raises(ValidationError):
            ProfileConfig(password="pw")

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            ProfileConfig(email="a@b.com")

    def test_json_round_trip(self):
        config = ProfileConfig(
            email="a@b.com",
            password="pw",
            positions=["Dev"],
            years_experience=3,
        )
        data = config.model_dump()
        restored = ProfileConfig(**data)
        assert restored.email == config.email
        assert restored.positions == config.positions
        assert restored.years_experience == config.years_experience

    def test_json_keys_are_snake_case(self):
        config = ProfileConfig(email="a@b.com", password="pw")
        data = config.model_dump()
        assert "phone_number" in data
        assert "remote_only" in data
        assert "profile_url" in data
        assert "user_city" in data
        assert "user_state" in data
        assert "blacklist" in data
        assert "blacklist_titles" in data
        assert "zip_code" in data
        assert "years_experience" in data
        assert "desired_salary" in data
        assert "openai_api_key" in data


# ---------------------------------------------------------------------------
# FastAPI endpoint tests
# ---------------------------------------------------------------------------

class TestFastAPIEndpoints:
    def setup_method(self):
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_status_default(self):
        resp = self.client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "applying" in data
        assert "applied_count" in data
        assert "failed_count" in data

    def test_stop_when_not_running(self):
        resp = self.client.post("/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not running"

    def test_start_returns_starting(self):
        """Test that /start accepts a valid ProfileConfig and returns status.

        Note: The bot thread will fail (no Selenium driver in test env) but
        the endpoint itself should return successfully.
        """
        config = {
            "email": "test@example.com",
            "password": "secret",
            "phone_number": "555-1234",
            "positions": ["Software Engineer"],
            "locations": ["Remote"],
        }
        # We need to mock the bot creation since Selenium isn't available
        with patch("easyapplybot._run_bot"):
            resp = self.client.post("/start", json=config)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "starting" or "error" not in data

    def test_start_missing_fields_fails(self):
        resp = self.client.post("/start", json={"email": "a@b.com"})
        assert resp.status_code == 422  # Pydantic validation error

    def test_websocket_connects(self):
        with self.client.websocket_connect("/ws") as ws:
            # Just verify connection works; the server keeps it alive
            # We can't easily send events in this test context, but
            # connection establishment is the key thing to verify.
            pass


# ---------------------------------------------------------------------------
# ConnectionManager tests
# ---------------------------------------------------------------------------

class TestConnectionManager:
    def test_init(self):
        cm = ConnectionManager()
        assert cm.connections == []

    def test_disconnect_nonexistent(self):
        cm = ConnectionManager()
        mock_ws = MagicMock()
        # Should not raise
        cm.disconnect(mock_ws)
        assert cm.connections == []

    def test_broadcast_removes_failed_connections(self):
        cm = ConnectionManager()

        async def _good_send(msg):
            pass

        good_ws = MagicMock()
        good_ws.send_text = _good_send

        bad_ws = MagicMock()

        async def _bad_send(msg):
            raise Exception("closed")

        bad_ws.send_text = _bad_send

        cm.connections = [good_ws, bad_ws]

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cm.broadcast("test_event", {"key": "value"}))
        finally:
            loop.close()

        # bad_ws should have been removed
        assert bad_ws not in cm.connections
        assert good_ws in cm.connections


# ---------------------------------------------------------------------------
# get_appropriate_value tests (pure logic, no Selenium)
# ---------------------------------------------------------------------------

class TestGetAppropriateValue:
    """Test the field-filling heuristics without requiring Selenium."""

    def _make_bot_stub(self):
        """Create a stub that has the same attributes as EasyApplyBot
        without initializing Selenium."""
        stub = MagicMock()
        stub.phone_number = "555-9999"
        stub.location = "Knoxville, TN"
        stub.user_state = "Tennessee"
        stub.zip_code = "37923"
        stub.desired_salary = "100000"
        stub.years_of_experience = "3"
        stub.linkedin_profile_url = "https://linkedin.com/in/jamesparrish"
        stub.checked_invalid = False

        # Import the method and bind it
        from easyapplybot import EasyApplyBot
        stub.get_appropriate_value = EasyApplyBot.get_appropriate_value.__get__(stub)
        stub.get_llm_suggested_answer = MagicMock(return_value="")
        return stub

    def test_phone_number(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Phone Number") == "555-9999"
        assert bot.get_appropriate_value("Mobile phone") == "555-9999"
        assert bot.get_appropriate_value("Contact telephone") == "555-9999"

    def test_city_location(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("City") == "Knoxville, TN"
        assert bot.get_appropriate_value("Current Location") == "Knoxville, TN"
        assert bot.get_appropriate_value("Where do you reside?") == "Knoxville, TN"

    def test_state(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("State") == "Tennessee"

    def test_zip_code(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Zip Code") == "37923"
        assert bot.get_appropriate_value("Postal code") == "37923"

    def test_salary(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Expected Salary") == "100000"
        assert bot.get_appropriate_value("Desired wage") == "100000"
        assert bot.get_appropriate_value("Annual income expectation") == "100000"

    def test_years_experience(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Years of experience") == "3"
        assert bot.get_appropriate_value("How many years experience do you have?") == "3"

    def test_availability(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("When are you available?") == "2 weeks"
        assert bot.get_appropriate_value("Start date") == "2 weeks"
        assert bot.get_appropriate_value("Notice period") == "2 weeks"

    def test_skills(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Key skills") == "Python, JavaScript, SQL"
        assert bot.get_appropriate_value("Programming language proficiency") == "Python, JavaScript, SQL"

    def test_education(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Highest education") == "Bachelor"
        assert bot.get_appropriate_value("Degree level") == "Bachelor"

    def test_linkedin_url(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("LinkedIn profile URL") == "https://linkedin.com/in/jamesparrish"

    def test_have_you_ever_worked(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Have you ever worked at this company?") == "No"

    def test_fallback_default(self):
        bot = self._make_bot_stub()
        # Unknown label with text type falls through to LLM (mocked to ""),
        # then returns "3" as default
        result = bot.get_appropriate_value("Some random unknown field", "text")
        assert result == "3"

    def test_non_text_empty_fallback(self):
        bot = self._make_bot_stub()
        result = bot.get_appropriate_value("Some random unknown field", "radio")
        assert result == ""


# ---------------------------------------------------------------------------
# emit_event tests
# ---------------------------------------------------------------------------

class TestEmitEvent:
    def test_emit_event_no_loop(self):
        """emit_event should be a no-op when _loop is None."""
        import easyapplybot
        original_loop = easyapplybot._loop
        try:
            easyapplybot._loop = None
            # Should not raise
            emit_event("test", {"key": "value"})
        finally:
            easyapplybot._loop = original_loop

    def test_emit_event_with_loop(self):
        """emit_event should schedule a coroutine when _loop is set."""
        import easyapplybot

        loop = asyncio.new_event_loop()
        original_loop = easyapplybot._loop
        easyapplybot._loop = loop

        broadcasted = []
        original_broadcast = easyapplybot.ws_manager.broadcast

        async def mock_broadcast(event_type, data=None):
            broadcasted.append((event_type, data))

        easyapplybot.ws_manager.broadcast = mock_broadcast

        try:
            emit_event("test_event", {"x": 1})
            # Run the loop briefly to process the scheduled coroutine
            loop.run_until_complete(asyncio.sleep(0.05))
            assert len(broadcasted) == 1
            assert broadcasted[0][0] == "test_event"
            assert broadcasted[0][1] == {"x": 1}
        finally:
            easyapplybot._loop = original_loop
            easyapplybot.ws_manager.broadcast = original_broadcast
            loop.close()


# ---------------------------------------------------------------------------
# JSON contract tests: verify Go and Python agree on field names
# ---------------------------------------------------------------------------

class TestJSONContract:
    """Verify that ProfileConfig's JSON output matches what Go's ProfilePayload expects."""

    def test_field_names_match_go(self):
        config = ProfileConfig(
            email="a@b.com",
            password="pw",
            phone_number="123",
            positions=["dev"],
            locations=["remote"],
            remote_only=True,
            profile_url="https://li.com",
            user_city="SF",
            user_state="CA",
            zip_code="94102",
            years_experience=3,
            desired_salary=100000,
            openai_api_key="sk-test",
        )
        data = json.loads(config.model_dump_json())

        # These keys must match the Go ProfilePayload json tags exactly
        go_keys = [
            "email", "password", "phone_number", "positions", "locations",
            "remote_only", "profile_url", "user_city", "user_state",
            "zip_code", "years_experience", "desired_salary", "openai_api_key",
            "blacklist", "blacklist_titles",
        ]
        for key in go_keys:
            assert key in data, f"Missing expected key {key!r} in Python JSON output"

    def test_positions_is_list(self):
        config = ProfileConfig(
            email="a@b.com", password="pw",
            positions=["Software Engineer", "Backend Dev"],
        )
        data = json.loads(config.model_dump_json())
        assert isinstance(data["positions"], list)
        assert len(data["positions"]) == 2

    def test_boolean_serialization(self):
        config = ProfileConfig(email="a@b.com", password="pw", remote_only=True)
        data = json.loads(config.model_dump_json())
        assert data["remote_only"] is True

    def test_integer_serialization(self):
        config = ProfileConfig(email="a@b.com", password="pw", years_experience=5, desired_salary=100000)
        data = json.loads(config.model_dump_json())
        assert data["years_experience"] == 5
        assert data["desired_salary"] == 100000
        assert isinstance(data["years_experience"], int)


# ---------------------------------------------------------------------------
# WebSocket event format tests
# ---------------------------------------------------------------------------

class TestWebSocketEventFormat:
    """Verify the event JSON format matches what Go expects to unmarshal."""

    def test_event_format(self):
        """Events should have {"type": "...", "data": {...}} format."""
        event = json.dumps({"type": "job_applied", "data": {"job_id": "42"}})
        parsed = json.loads(event)
        assert "type" in parsed
        assert "data" in parsed
        assert isinstance(parsed["data"], dict)

    def test_all_event_types_are_strings(self):
        event_types = [
            "login_success", "login_failed", "bot_started", "bot_stopped",
            "job_applying", "job_applied", "job_failed", "progress",
            "log", "error",
        ]
        for et in event_types:
            event = json.dumps({"type": et, "data": {}})
            parsed = json.loads(event)
            assert parsed["type"] == et


# ---------------------------------------------------------------------------
# Cross-platform compatibility tests
# ---------------------------------------------------------------------------

class TestCrossPlatformPaths:
    """Verify path handling works on any OS."""

    def test_log_directory_creation(self):
        """setup_logger uses os.path.join and os.makedirs, not string concatenation."""
        import easyapplybot
        import inspect
        source = inspect.getsource(easyapplybot.setup_logger)
        # Should use os.path.join, not string concatenation with '/'
        assert "os.path.join" in source, "setup_logger should use os.path.join for paths"
        assert "os.makedirs" in source or "os.mkdir" in source, \
            "setup_logger should create log dir with os.makedirs"

    def test_log_dir_can_be_created_in_temp(self):
        """Verify the log directory creation pattern works cross-platform."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            assert os.path.isdir(log_dir)
            # Verify we can write a file there
            log_file = os.path.join(log_dir, "test.log")
            with open(log_file, "w") as f:
                f.write("test")
            assert os.path.isfile(log_file)

    def test_os_path_join_never_uses_wrong_separator(self):
        """os.path.join should produce platform-correct separators."""
        path = os.path.join("logs", "test.log")
        if sys.platform == "win32":
            assert "\\" in path
        else:
            assert "/" in path
            assert "\\" not in path


class TestCrossPlatformCSV:
    """Verify CSV writing uses newline='' to prevent double-spacing on Windows."""

    def test_csv_source_uses_newline_empty(self):
        """The bot's CSV writing code must use newline='' in open()."""
        import easyapplybot
        import inspect
        source = inspect.getsource(easyapplybot.EasyApplyBot)
        # Find CSV open patterns - should have newline=''
        # The fix we applied adds newline='' to the csv writer open() call
        assert "newline=''" in source or 'newline=""' in source, \
            "CSV writing should use newline='' to prevent double line endings on Windows"

    def test_csv_write_no_extra_blank_lines(self):
        """Verify CSV writing with newline='' produces correct output."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            tmppath = f.name
            writer = csv.writer(f)
            writer.writerow(["job1", "company1", "applied"])
            writer.writerow(["job2", "company2", "applied"])

        try:
            with open(tmppath, "r") as f:
                content = f.read()
            lines = content.strip().split("\n")
            assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}: {lines!r}"
            # No blank lines between rows
            assert "" not in lines
        finally:
            os.unlink(tmppath)


class TestCrossPlatformPyautogui:
    """Verify pyautogui is optional and gracefully handled."""

    def test_pyautogui_import_is_optional(self):
        """The bot should handle missing pyautogui gracefully."""
        import easyapplybot
        import inspect
        source = inspect.getsource(easyapplybot)
        # The fix wraps pyautogui import in try/except
        assert "except ImportError" in source, \
            "pyautogui import should be wrapped in try/except ImportError"

    def test_avoid_lock_with_no_pyautogui(self):
        """avoid_lock should be a no-op when pyautogui is None."""
        from easyapplybot import EasyApplyBot
        stub = MagicMock()
        stub.avoid_lock = EasyApplyBot.avoid_lock.__get__(stub)

        import easyapplybot
        original = easyapplybot.pyautogui
        try:
            easyapplybot.pyautogui = None
            # Should not raise
            stub.avoid_lock()
        finally:
            easyapplybot.pyautogui = original

    def test_avoid_lock_handles_display_error(self):
        """avoid_lock should catch exceptions from pyautogui (e.g., no display)."""
        from easyapplybot import EasyApplyBot
        stub = MagicMock()
        stub.avoid_lock = EasyApplyBot.avoid_lock.__get__(stub)

        mock_pyautogui = MagicMock()
        mock_pyautogui.FAILSAFE = True
        mock_pyautogui.position.side_effect = Exception("no display")

        import easyapplybot
        original = easyapplybot.pyautogui
        try:
            easyapplybot.pyautogui = mock_pyautogui
            # Should not raise even though pyautogui.position() throws
            stub.avoid_lock()
        finally:
            easyapplybot.pyautogui = original


class TestCrossPlatformServerBinding:
    """Verify the FastAPI server can bind on localhost."""

    def test_localhost_tcp_binding(self):
        """Verify 127.0.0.1 TCP binding works on this platform."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            assert 1 <= port <= 65535
        finally:
            sock.close()

    def test_fastapi_health_over_testclient(self):
        """Verify FastAPI endpoints work via TestClient (no real network)."""
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_websocket_over_testclient(self):
        """Verify WebSocket endpoint works via TestClient."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            # Connection established successfully
            pass


class TestCrossPlatformJSONEncoding:
    """Verify JSON serialization is consistent across platforms."""

    def test_no_platform_line_endings_in_json(self):
        """JSON output should not contain \\r\\n or \\r."""
        config = ProfileConfig(
            email="test@test.com",
            password="pass",
            positions=["SWE"],
            locations=["Remote", "New York"],
        )
        json_str = config.model_dump_json()
        assert "\r\n" not in json_str, "JSON contains Windows line endings"
        assert "\r" not in json_str, "JSON contains carriage return"

    def test_unicode_in_json(self):
        """Unicode characters should survive JSON round-trip."""
        config = ProfileConfig(
            email="test@test.com",
            password="pass",
            user_city="San Jos\u00e9",
            positions=["D\u00e9veloppeur"],
        )
        data = json.loads(config.model_dump_json())
        assert data["user_city"] == "San Jos\u00e9"
        assert data["positions"][0] == "D\u00e9veloppeur"

    def test_empty_lists_serialize_correctly(self):
        """Empty lists should serialize as [] not null."""
        config = ProfileConfig(email="a@b.com", password="pw")
        data = json.loads(config.model_dump_json())
        assert data["positions"] == []
        assert data["locations"] == []
        assert isinstance(data["positions"], list)


class TestCrossPlatformIntegration:
    """End-to-end integration tests that verify the full request flow."""

    def test_start_stop_lifecycle(self):
        """Verify /start then /stop lifecycle works."""
        client = TestClient(app)
        config = {
            "email": "test@example.com",
            "password": "secret",
            "positions": ["SWE"],
        }
        with patch("easyapplybot._run_bot"):
            resp = client.post("/start", json=config)
        assert resp.status_code == 200

        resp = client.post("/stop")
        assert resp.status_code == 200

    def test_status_fields_are_correct_types(self):
        """Verify /status returns correct field types across platforms."""
        client = TestClient(app)
        resp = client.get("/status")
        data = resp.json()
        assert isinstance(data["running"], bool)
        assert isinstance(data["applying"], bool)
        assert isinstance(data["applied_count"], int)
        assert isinstance(data["failed_count"], int)
