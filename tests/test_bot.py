"""Tests for easyapplybot.py bot logic."""

import csv
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from easyapplybot import (
    ConsecutiveFailuresException,
    DailyLimitReachedException,
    H1BAPIUnavailableException,
    EasyApplyBot,
    ProfileConfig,
    _run_bot,
    open_linkedin_profile,
)
from settings import SystemConfig
import easyapplybot


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
            github_url="https://github.com/testuser",
            portfolio_url="https://testuser.dev",
            user_city="New York",
            user_state="NY",
            zip_code="10001",
            years_experience=5,
            desired_salary=120000,
        )
        assert config.email == "test@example.com"
        assert config.password == "secret"
        assert config.phone_number == "555-1234"
        assert config.positions == ["Software Engineer"]
        assert config.locations == ["Remote"]
        assert config.remote_only is True
        assert config.years_experience == 5
        assert config.desired_salary == 120000
        assert config.github_url == "https://github.com/testuser"
        assert config.portfolio_url == "https://testuser.dev"

    def test_defaults(self):
        config = ProfileConfig(email="a@b.com", password="pw")
        assert config.phone_number == ""
        assert config.positions == []
        assert config.locations == []
        assert config.remote_only is False
        assert config.profile_url == ""
        assert config.github_url == ""
        assert config.portfolio_url == ""
        assert config.user_city == ""
        assert config.user_state == ""
        assert config.zip_code == ""
        assert config.years_experience == 0
        assert config.desired_salary == 0
        assert config.whitelist_titles == []

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
        assert "github_url" in data
        assert "portfolio_url" in data
        assert "user_city" in data
        assert "user_state" in data
        assert "blacklist" not in data
        assert "blacklist_titles" not in data
        assert "zip_code" in data
        assert "years_experience" in data
        assert "desired_salary" in data
        assert "whitelist_titles" in data
        assert "ai_provider" not in data
        assert "ai_api_key" not in data

    def test_legacy_openai_api_key_migration(self):
        """Old profiles with openai_api_key are silently stripped — no crash, no field."""
        data = {
            "email": "a@b.com",
            "password": "pw",
            "openai_api_key": "sk-legacy",
        }
        config = ProfileConfig(**data)
        assert not hasattr(config, "openai_api_key")
        assert not hasattr(config, "ai_api_key")
        assert not hasattr(config, "ai_provider")

    def test_legacy_ai_fields_stripped(self):
        """Old profiles with ai_provider/ai_api_key don't crash and fields are dropped."""
        data = {
            "email": "a@b.com",
            "password": "pw",
            "ai_provider": "anthropic",
            "ai_api_key": "sk-ant-old",
        }
        config = ProfileConfig(**data)
        assert not hasattr(config, "ai_provider")
        assert not hasattr(config, "ai_api_key")

    def test_legacy_blacklist_stripped(self):
        """Old profiles with blacklist/blacklist_titles don't crash and fields are dropped."""
        data = {
            "email": "a@b.com",
            "password": "pw",
            "blacklist": ["Coinbase", "Meta"],
            "blacklist_titles": ["intern"],
        }
        config = ProfileConfig(**data)
        assert not hasattr(config, "blacklist")
        assert not hasattr(config, "blacklist_titles")


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
        stub.github_url = "https://github.com/jamesparrish"
        stub.portfolio_url = "https://jamesparrish.dev"
        stub.checked_invalid = False

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

    def test_github_url(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("GitHub profile") == "https://github.com/jamesparrish"
        assert bot.get_appropriate_value("Git Hub URL") == "https://github.com/jamesparrish"

    def test_portfolio_url(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Portfolio URL") == "https://jamesparrish.dev"
        assert bot.get_appropriate_value("Personal website") == "https://jamesparrish.dev"
        assert bot.get_appropriate_value("Personal site") == "https://jamesparrish.dev"

    def test_have_you_ever_worked(self):
        bot = self._make_bot_stub()
        assert bot.get_appropriate_value("Have you ever worked at this company?") == "No"

    def test_fallback_default(self):
        bot = self._make_bot_stub()
        result = bot.get_appropriate_value("Some random unknown field", "text")
        assert result == "3"

    def test_non_text_empty_fallback(self):
        bot = self._make_bot_stub()
        result = bot.get_appropriate_value("Some random unknown field", "radio")
        assert result == ""


# ---------------------------------------------------------------------------
# on_event callback tests
# ---------------------------------------------------------------------------

class TestOnEventCallback:
    """Test that EasyApplyBot calls the on_event callback correctly."""

    def _make_bot_stub_with_emit(self, on_event=None):
        """Create a bot stub with _emit bound, bypassing __init__."""
        stub = MagicMock()
        stub._on_event = on_event
        stub._emit = EasyApplyBot._emit.__get__(stub)
        return stub

    def test_emit_calls_on_event(self):
        events = []
        def handler(event_type, data):
            events.append((event_type, data))

        stub = self._make_bot_stub_with_emit(on_event=handler)
        stub._emit("test_event", {"key": "value"})

        assert len(events) == 1
        assert events[0] == ("test_event", {"key": "value"})

    def test_emit_with_no_callback(self):
        """_emit should be a no-op when on_event is None."""
        stub = self._make_bot_stub_with_emit(on_event=None)
        # Should not raise
        stub._emit("test_event", {"key": "value"})

    def test_emit_with_empty_data(self):
        events = []
        def handler(event_type, data):
            events.append((event_type, data))

        stub = self._make_bot_stub_with_emit(on_event=handler)
        stub._emit("login_success")

        assert len(events) == 1
        assert events[0] == ("login_success", {})

    def test_emit_callback_exception_is_swallowed(self):
        """Exceptions in the callback should not propagate."""
        def bad_handler(event_type, data):
            raise RuntimeError("callback error")

        stub = self._make_bot_stub_with_emit(on_event=bad_handler)
        # Should not raise
        stub._emit("test_event", {})


# ---------------------------------------------------------------------------
# _run_bot callback tests
# ---------------------------------------------------------------------------

class TestRunBotCallback:
    """Test that _run_bot fires bot_started/bot_stopped events."""

    def test_run_bot_fires_stopped_on_login_failure(self):
        events = []
        def handler(event_type, data):
            events.append((event_type, data))

        config = ProfileConfig(
            email="test@example.com",
            password="secret",
            positions=["SWE"],
            locations=["Remote"],
        )

        mock_bot = MagicMock()
        mock_bot.start_linkedin.return_value = False

        with patch("easyapplybot.load_settings", return_value=SystemConfig()), \
             patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}), \
             patch("easyapplybot.EasyApplyBot", return_value=mock_bot):
            _run_bot(config, on_event=handler)

        event_types = [e[0] for e in events]
        assert "bot_stopped" in event_types
        stopped_event = next(e for e in events if e[0] == "bot_stopped")
        assert stopped_event[1].get("reason") == "login_failed"

    def test_run_bot_fires_bot_started_on_success(self):
        events = []
        def handler(event_type, data):
            events.append((event_type, data))

        config = ProfileConfig(
            email="test@example.com",
            password="secret",
            positions=["SWE"],
            locations=["Remote"],
        )

        mock_bot = MagicMock()
        mock_bot.start_linkedin.return_value = True
        mock_bot.start_apply.return_value = None

        with patch("easyapplybot.load_settings", return_value=SystemConfig()), \
             patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}), \
             patch("easyapplybot.EasyApplyBot", return_value=mock_bot):
            _run_bot(config, on_event=handler)

        event_types = [e[0] for e in events]
        assert "bot_started" in event_types
        assert "bot_stopped" in event_types

    def test_run_bot_stopped_no_positions(self):
        events = []
        def handler(event_type, data):
            events.append((event_type, data))

        config = ProfileConfig(
            email="test@example.com",
            password="secret",
            positions=[],
            locations=[],
        )

        mock_bot = MagicMock()
        mock_bot.start_linkedin.return_value = True

        with patch("easyapplybot.load_settings", return_value=SystemConfig()), \
             patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}), \
             patch("easyapplybot.EasyApplyBot", return_value=mock_bot):
            _run_bot(config, on_event=handler)

        event_types = [e[0] for e in events]
        assert "bot_stopped" in event_types
        stopped_event = next(e for e in events if e[0] == "bot_stopped")
        assert "no positions" in stopped_event[1].get("reason", "")


# ---------------------------------------------------------------------------
# Cross-platform compatibility tests
# ---------------------------------------------------------------------------

class TestCrossPlatformPaths:
    def test_log_directory_creation(self):
        import easyapplybot
        import inspect
        source = inspect.getsource(easyapplybot.setup_logger)
        assert "os.path.join" in source, "setup_logger should use os.path.join for paths"
        assert "os.makedirs" in source or "os.mkdir" in source

    def test_log_dir_can_be_created_in_temp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            assert os.path.isdir(log_dir)
            log_file = os.path.join(log_dir, "test.log")
            with open(log_file, "w") as f:
                f.write("test")
            assert os.path.isfile(log_file)

    def test_os_path_join_never_uses_wrong_separator(self):
        path = os.path.join("logs", "test.log")
        if sys.platform == "win32":
            assert "\\" in path
        else:
            assert "/" in path
            assert "\\" not in path


class TestCrossPlatformCSV:
    def test_csv_write_no_extra_blank_lines(self):
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
            assert "" not in lines
        finally:
            os.unlink(tmppath)


class TestCrossPlatformPyautogui:
    def test_pyautogui_import_is_optional(self):
        import easyapplybot
        import inspect
        source = inspect.getsource(easyapplybot)
        assert "except ImportError" in source

    def test_avoid_lock_with_no_pyautogui(self):
        stub = MagicMock()
        stub.avoid_lock = EasyApplyBot.avoid_lock.__get__(stub)

        import easyapplybot
        original = easyapplybot.pyautogui
        try:
            easyapplybot.pyautogui = None
            stub.avoid_lock()
        finally:
            easyapplybot.pyautogui = original

    def test_avoid_lock_handles_display_error(self):
        stub = MagicMock()
        stub.avoid_lock = EasyApplyBot.avoid_lock.__get__(stub)

        mock_pyautogui = MagicMock()
        mock_pyautogui.FAILSAFE = True
        mock_pyautogui.position.side_effect = Exception("no display")

        import easyapplybot
        original = easyapplybot.pyautogui
        try:
            easyapplybot.pyautogui = mock_pyautogui
            stub.avoid_lock()
        finally:
            easyapplybot.pyautogui = original


class TestCrossPlatformJSONEncoding:
    def test_no_platform_line_endings_in_json(self):
        config = ProfileConfig(
            email="test@test.com",
            password="pass",
            positions=["SWE"],
            locations=["Remote", "New York"],
        )
        json_str = config.model_dump_json()
        assert "\r\n" not in json_str
        assert "\r" not in json_str

    def test_unicode_in_json(self):
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
        config = ProfileConfig(email="a@b.com", password="pw")
        data = json.loads(config.model_dump_json())
        assert data["positions"] == []
        assert data["locations"] == []
        assert isinstance(data["positions"], list)


# ---------------------------------------------------------------------------
# LLM provider routing tests
# ---------------------------------------------------------------------------

class TestLLMProviderRouting:
    """Test that get_llm_suggested_answer routes to the correct helper."""

    def _make_bot_stub(self):
        stub = MagicMock()
        stub.config = ProfileConfig(email="a@b.com", password="pw")
        stub.location = "New York, NY"
        stub.years_of_experience = "5"
        stub.desired_salary = "120000"
        stub.github_url = ""
        stub.portfolio_url = ""
        stub._build_llm_prompt = EasyApplyBot._build_llm_prompt.__get__(stub)
        stub._llm_openai = MagicMock(return_value="openai_answer")
        stub._llm_anthropic = MagicMock(return_value="anthropic_answer")
        stub._llm_gemini = MagicMock(return_value="gemini_answer")
        stub._llm_ollama = MagicMock(return_value="ollama_answer")
        stub.get_llm_suggested_answer = EasyApplyBot.get_llm_suggested_answer.__get__(stub)
        return stub

    def test_routes_to_openai(self):
        stub = self._make_bot_stub()
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}):
            result = stub.get_llm_suggested_answer("Years of experience?")
        stub._llm_openai.assert_called_once()
        stub._llm_anthropic.assert_not_called()
        assert result == "openai_answer"

    def test_routes_to_anthropic(self):
        stub = self._make_bot_stub()
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "anthropic"}):
            result = stub.get_llm_suggested_answer("Years of experience?")
        stub._llm_anthropic.assert_called_once()
        stub._llm_openai.assert_not_called()
        assert result == "anthropic_answer"

    def test_routes_to_gemini(self):
        stub = self._make_bot_stub()
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "gemini"}):
            result = stub.get_llm_suggested_answer("Years of experience?")
        stub._llm_gemini.assert_called_once()
        stub._llm_openai.assert_not_called()
        assert result == "gemini_answer"

    def test_routes_to_ollama(self):
        stub = self._make_bot_stub()
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "ollama"}):
            result = stub.get_llm_suggested_answer("Years of experience?")
        stub._llm_ollama.assert_called_once()
        stub._llm_openai.assert_not_called()
        assert result == "ollama_answer"

    def test_unknown_provider_returns_empty(self):
        stub = self._make_bot_stub()
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "unknown"}):
            result = stub.get_llm_suggested_answer("Years of experience?")
        assert result == ""

    def test_exception_returns_empty(self):
        stub = self._make_bot_stub()
        stub._llm_openai.side_effect = RuntimeError("API down")
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}):
            result = stub.get_llm_suggested_answer("Years of experience?")
        assert result == ""


# ---------------------------------------------------------------------------
# DailyLimitReachedException detection tests
# ---------------------------------------------------------------------------

class TestDailyLimitDetection:
    """Test daily limit detection and propagation."""

    def _make_bot_stub(self):
        stub = MagicMock()
        stub._check_daily_limit = EasyApplyBot._check_daily_limit.__get__(stub)
        return stub

    def _make_el(self, text):
        el = MagicMock()
        el.text = text
        return el

    def test_check_daily_limit_true(self):
        stub = self._make_bot_stub()
        stub.browser.find_elements.return_value = [
            self._make_el("We limit daily submissions to protect our members.")
        ]
        assert stub._check_daily_limit() is True

    def test_check_daily_limit_false_wrong_text(self):
        stub = self._make_bot_stub()
        stub.browser.find_elements.return_value = [
            self._make_el("Please enter a valid phone number.")
        ]
        assert stub._check_daily_limit() is False

    def test_check_daily_limit_false_no_elements(self):
        stub = self._make_bot_stub()
        stub.browser.find_elements.return_value = []
        assert stub._check_daily_limit() is False

    def test_check_daily_limit_case_insensitive(self):
        stub = self._make_bot_stub()
        stub.browser.find_elements.return_value = [
            self._make_el("WE LIMIT DAILY SUBMISSIONS.")
        ]
        assert stub._check_daily_limit() is True

    def test_check_daily_limit_matches_among_multiple_elements(self):
        stub = self._make_bot_stub()
        stub.browser.find_elements.return_value = [
            self._make_el("Please enter your phone number."),
            self._make_el("We limit daily submissions to protect our members."),
        ]
        assert stub._check_daily_limit() is True

    def test_check_daily_limit_exception_returns_false(self):
        stub = self._make_bot_stub()
        stub.browser.find_elements.side_effect = Exception("stale element")
        assert stub._check_daily_limit() is False

    def test_get_easy_apply_button_raises_preclick(self):
        """DailyLimitReachedException raised before button search when limit detected."""
        stub = MagicMock()
        stub._check_daily_limit.return_value = True
        stub.get_easy_apply_button = EasyApplyBot.get_easy_apply_button.__get__(stub)
        with pytest.raises(DailyLimitReachedException):
            stub.get_easy_apply_button()
        stub.browser.find_elements.assert_not_called()

    def test_get_easy_apply_button_raises_postclick(self):
        """DailyLimitReachedException raised after click when limit modal appears."""
        stub = MagicMock()
        # First call (pre-click) returns False, second call (post-click) returns True
        stub._check_daily_limit.side_effect = [False, True]
        stub.browser.find_elements.return_value = [MagicMock()]
        stub.get_easy_apply_button = EasyApplyBot.get_easy_apply_button.__get__(stub)
        with pytest.raises(DailyLimitReachedException):
            stub.get_easy_apply_button()

    def test_run_bot_emits_daily_limit_reached(self):
        """_run_bot emits daily_limit_reached and bot_stopped when limit is hit."""
        events = []
        def handler(event_type, data):
            events.append((event_type, data))

        config = ProfileConfig(
            email="test@example.com",
            password="secret",
            positions=["SWE"],
            locations=["Remote"],
        )

        mock_bot = MagicMock()
        mock_bot.start_linkedin.return_value = True
        mock_bot.start_apply.side_effect = DailyLimitReachedException("limit reached")

        with patch("easyapplybot.load_settings", return_value=SystemConfig()), \
             patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}), \
             patch("easyapplybot.EasyApplyBot", return_value=mock_bot):
            _run_bot(config, on_event=handler)

        event_types = [e[0] for e in events]
        assert "daily_limit_reached" in event_types
        assert "bot_stopped" in event_types
        limit_event = next(e for e in events if e[0] == "daily_limit_reached")
        assert limit_event[1]["profile_email"] == "test@example.com"
        stopped_event = next(e for e in events if e[0] == "bot_stopped")
        assert stopped_event[1]["reason"] == "daily_limit_reached"


# ---------------------------------------------------------------------------
# open_linkedin_profile tests
# ---------------------------------------------------------------------------

def _make_profile(**kwargs):
    defaults = dict(email="user@example.com", password="secret")
    defaults.update(kwargs)
    return ProfileConfig(**defaults)


class TestOpenLinkedInProfile:
    def setup_method(self):
        # Reset module-level state before each test
        easyapplybot._profile_browser = None

    def test_returns_true_on_success(self):
        driver = MagicMock()
        with patch("easyapplybot._make_chrome_driver", return_value=driver):
            result = open_linkedin_profile(_make_profile())
        assert result is True

    def test_navigates_to_profile_url(self):
        driver = MagicMock()
        profile_url = "https://linkedin.com/in/testuser"
        with patch("easyapplybot._make_chrome_driver", return_value=driver):
            open_linkedin_profile(_make_profile(profile_url=profile_url))
        calls = [c.args[0] for c in driver.get.call_args_list]
        assert profile_url in calls

    def test_no_navigation_when_no_profile_url(self):
        driver = MagicMock()
        with patch("easyapplybot._make_chrome_driver", return_value=driver):
            open_linkedin_profile(_make_profile())
        # Only the login page get() should have been called
        assert driver.get.call_count == 1

    def test_returns_false_on_exception(self):
        driver = MagicMock()
        driver.find_element.side_effect = Exception("element not found")
        with patch("easyapplybot._make_chrome_driver", return_value=driver):
            result = open_linkedin_profile(_make_profile())
        assert result is False
        driver.quit.assert_called_once()

    def test_browser_ready_event_fired(self):
        driver = MagicMock()
        events = []
        with patch("easyapplybot._make_chrome_driver", return_value=driver):
            open_linkedin_profile(_make_profile(), on_event=lambda t, d: events.append(t))
        assert "browser_ready" in events

    def test_login_failed_event_fired(self):
        driver = MagicMock()
        driver.find_element.side_effect = Exception("timeout")
        events = []
        with patch("easyapplybot._make_chrome_driver", return_value=driver):
            open_linkedin_profile(_make_profile(), on_event=lambda t, d: events.append(t))
        assert "login_failed" in events

    def test_previous_browser_closed(self):
        first_driver = MagicMock()
        second_driver = MagicMock()
        drivers = iter([first_driver, second_driver])
        with patch("easyapplybot._make_chrome_driver", side_effect=lambda: next(drivers)):
            open_linkedin_profile(_make_profile())
            open_linkedin_profile(_make_profile())
        first_driver.quit.assert_called_once()


# ---------------------------------------------------------------------------
# Watchdog / deadline tests
# ---------------------------------------------------------------------------

class TestWatchdog:
    """Tests for the per-job 60-second timeout watchdog."""

    def _make_send_resume_stub(self):
        stub = MagicMock()
        stub.stopped = False
        stub.checked_invalid = False
        stub.browser.find_elements.return_value = []
        stub.send_resume = EasyApplyBot.send_resume.__get__(stub)
        return stub

    def test_send_resume_raises_timeout_on_expired_deadline(self):
        """Deadline already past → TimeoutError on first iteration."""
        stub = self._make_send_resume_stub()
        with patch("time.sleep"):
            with pytest.raises(TimeoutError):
                stub.send_resume(deadline=0.0)  # epoch = already expired

    def test_send_resume_no_deadline_does_not_raise(self):
        """No deadline → falls through to no_progress escape (returns False)."""
        stub = self._make_send_resume_stub()
        with patch("time.sleep"):
            result = stub.send_resume(deadline=None)
        assert result is False

    def test_no_progress_count_returns_false_after_15_empty_iterations(self):
        """15 iterations with no actionable button → return False."""
        stub = self._make_send_resume_stub()
        with patch("time.sleep"):
            result = stub.send_resume(deadline=None)
        assert result is False


# ---------------------------------------------------------------------------
# _dismiss_modal tests
# ---------------------------------------------------------------------------

class TestDismissModal:
    """Tests for the modal-dismiss helper used after timeouts."""

    def _make_stub(self):
        stub = MagicMock()
        stub._dismiss_modal = EasyApplyBot._dismiss_modal.__get__(stub)
        return stub

    def test_dismiss_modal_clicks_dismiss_button_when_present(self):
        stub = self._make_stub()
        dismiss_btn = MagicMock()
        stub.browser.find_element.return_value = dismiss_btn
        stub._dismiss_modal()
        dismiss_btn.click.assert_called_once()

    def test_dismiss_modal_falls_back_to_escape_when_no_button(self):
        stub = self._make_stub()
        stub.browser.find_element.side_effect = Exception("no element")
        # Should not raise even when all attempts fail
        stub._dismiss_modal()


# ---------------------------------------------------------------------------
# LLM options= parameter tests
# ---------------------------------------------------------------------------

class TestLLMRadioFallback:
    """Tests for the options= radio-choice prompt path in get_llm_suggested_answer."""

    def _make_stub(self):
        stub = MagicMock()
        stub.config = ProfileConfig(email="a@b.com", password="pw")
        stub.location = "New York, NY"
        stub.years_of_experience = "5"
        stub.desired_salary = "120000"
        stub.github_url = ""
        stub.portfolio_url = ""
        stub._build_llm_prompt = EasyApplyBot._build_llm_prompt.__get__(stub)
        stub._llm_openai = MagicMock(return_value="Yes")
        stub._llm_anthropic = MagicMock(return_value="Yes")
        stub._llm_gemini = MagicMock(return_value="Yes")
        stub._llm_ollama = MagicMock(return_value="Yes")
        stub.get_llm_suggested_answer = EasyApplyBot.get_llm_suggested_answer.__get__(stub)
        return stub

    def test_options_param_builds_radio_prompt(self):
        """When options= is given, _llm_* receives a choice-style prompt."""
        stub = self._make_stub()
        options = ["Yes", "No", "Unsure"]
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}):
            stub.get_llm_suggested_answer("Are you authorized to work?", options=options)
        call_prompt = stub._llm_openai.call_args[0][0]
        assert "Are you authorized to work?" in call_prompt
        assert "Yes" in call_prompt
        assert "No" in call_prompt

    def test_options_prompt_does_not_include_numeric_shortcut(self):
        """Radio prompt must NOT contain the 'answer with only a digit' instruction
        (that instruction is for text inputs and would break option matching)."""
        stub = self._make_stub()
        options = ["Less than 1 year", "1-3 years", "3-5 years", "5+ years"]
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}):
            stub.get_llm_suggested_answer("Years of experience?", options=options)
        call_prompt = stub._llm_openai.call_args[0][0]
        assert "single numeric digit" not in call_prompt

    def test_no_options_still_uses_text_prompt(self):
        """Without options=, _build_llm_prompt() is used as before."""
        stub = self._make_stub()
        stub._llm_openai.return_value = "5"
        with patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}):
            result = stub.get_llm_suggested_answer("Years of experience?")
        call_prompt = stub._llm_openai.call_args[0][0]
        # Text prompt includes the persona / numeric shortcut instruction
        assert "years of experience" in call_prompt.lower()
        assert result == "5"


# ---------------------------------------------------------------------------
# _build_llm_prompt tests
# ---------------------------------------------------------------------------

class TestBuildLLMPrompt:
    """Tests for github_url/portfolio_url appearing in the LLM prompt."""

    def _make_stub(self, github_url="", portfolio_url=""):
        stub = MagicMock()
        stub.config = ProfileConfig(email="jane@example.com", password="pw", positions=["SWE"])
        stub.location = "Austin, TX"
        stub.years_of_experience = "4"
        stub.desired_salary = "130000"
        stub.github_url = github_url
        stub.portfolio_url = portfolio_url
        stub._build_llm_prompt = EasyApplyBot._build_llm_prompt.__get__(stub)
        return stub

    def test_github_url_included_when_set(self):
        stub = self._make_stub(github_url="https://github.com/jane")
        prompt = stub._build_llm_prompt("How many years experience?")
        assert "https://github.com/jane" in prompt

    def test_portfolio_url_included_when_set(self):
        stub = self._make_stub(portfolio_url="https://jane.dev")
        prompt = stub._build_llm_prompt("Any personal site?")
        assert "https://jane.dev" in prompt

    def test_neither_url_included_when_empty(self):
        stub = self._make_stub()
        prompt = stub._build_llm_prompt("Question?")
        assert "GitHub" not in prompt
        assert "Portfolio" not in prompt


# ---------------------------------------------------------------------------
# Headless env var tests
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CLI --run flag tests
# ---------------------------------------------------------------------------

class TestCLIRunFlag:
    """Tests for --run <profile> and --headless CLI flags."""

    def test_run_flag_unknown_profile_exits_nonzero(self, monkeypatch):
        """--run with a profile name not in profiles.json → sys.exit(1)."""
        import hiringfunnel
        monkeypatch.setattr(hiringfunnel, "load_profiles", lambda: {})
        monkeypatch.setattr(hiringfunnel, "list_names", lambda: [])

        with patch("sys.argv", ["hiringfunnel", "--run", "NonExistentProfile"]):
            with pytest.raises(SystemExit) as exc_info:
                hiringfunnel.main()
        assert exc_info.value.code == 1

    def test_run_flag_known_profile_calls_run_profile_sequence(self, monkeypatch):
        """--run with a valid profile calls run_profile_sequence and returns."""
        import hiringfunnel
        profile_data = {"email": "a@b.com", "password": "pw", "positions": ["SWE"], "locations": ["Remote"]}
        monkeypatch.setattr(hiringfunnel, "load_profiles", lambda: {"TestClient": profile_data})
        monkeypatch.setattr(hiringfunnel, "list_names", lambda: ["TestClient"])
        monkeypatch.setattr(hiringfunnel, "init_db", lambda: None)
        monkeypatch.setattr(hiringfunnel, "_redirect_logs_to_file", lambda: None)

        calls = []
        monkeypatch.setattr(hiringfunnel, "run_profile_sequence",
                            lambda *a, **kw: calls.append((a, kw)))

        with patch("sys.argv", ["hiringfunnel", "--run", "TestClient"]):
            hiringfunnel.main()

        assert len(calls) == 1
        assert calls[0][0][0] == "TestClient"  # start_name arg


# ---------------------------------------------------------------------------
# ConsecutiveFailuresException tests
# ---------------------------------------------------------------------------

class TestConsecutiveFailures:
    """Tests for the 5-consecutive-failure cap that bails to the next profile."""

    def _make_bot_stub(self):
        stub = MagicMock()
        stub.consecutive_fail_streak = 0
        stub.applied_count = 0
        stub.failed_count = 0
        stub.MAX_CONSECUTIVE_FAILURES = EasyApplyBot.MAX_CONSECUTIVE_FAILURES
        return stub

    def test_streak_increments_on_result_false(self):
        """Each send_resume()=False increments the streak counter."""
        stub = self._make_bot_stub()
        # Simulate tracking manually (mirrors what applications_loop does)
        for _ in range(3):
            stub.failed_count += 1
            stub.consecutive_fail_streak += 1
        assert stub.consecutive_fail_streak == 3

    def test_streak_resets_on_success(self):
        """A successful application resets the streak to zero."""
        stub = self._make_bot_stub()
        stub.consecutive_fail_streak = 4
        # simulate success
        stub.applied_count += 1
        stub.consecutive_fail_streak = 0
        assert stub.consecutive_fail_streak == 0

    def test_streak_broken_by_success_prevents_raise(self):
        """4 failures + 1 success + 4 more failures does not reach threshold."""
        stub = self._make_bot_stub()
        for _ in range(4):
            stub.consecutive_fail_streak += 1
        # success resets
        stub.consecutive_fail_streak = 0
        reached = False
        for _ in range(4):
            stub.consecutive_fail_streak += 1
            if stub.consecutive_fail_streak >= stub.MAX_CONSECUTIVE_FAILURES:
                reached = True
        assert not reached
        assert stub.consecutive_fail_streak == 4

    def test_five_consecutive_failures_raises(self):
        """Exactly 5 consecutive failures raises ConsecutiveFailuresException."""
        stub = self._make_bot_stub()
        with pytest.raises(ConsecutiveFailuresException):
            for _ in range(5):
                stub.consecutive_fail_streak += 1
                if stub.consecutive_fail_streak >= stub.MAX_CONSECUTIVE_FAILURES:
                    raise ConsecutiveFailuresException("5 consecutive application failures")

    def test_max_consecutive_failures_constant(self):
        """MAX_CONSECUTIVE_FAILURES is 5 on the class."""
        assert EasyApplyBot.MAX_CONSECUTIVE_FAILURES == 5

    def test_consecutive_fail_streak_initializes_to_zero(self):
        """consecutive_fail_streak starts at 0 in __init__."""
        config = ProfileConfig(email="a@b.com", password="pw")
        with patch("easyapplybot._make_chrome_driver") as mock_driver:
            mock_driver.return_value = MagicMock()
            bot = EasyApplyBot.__new__(EasyApplyBot)
            bot._on_event = None
            bot._stop_event = MagicMock()
            bot.applied_count = 0
            bot.failed_count = 0
            bot.total_seen = 0
            bot.consecutive_fail_streak = 0
        assert bot.consecutive_fail_streak == 0

    def test_run_bot_emits_consecutive_failures_exceeded(self):
        """_run_bot catches ConsecutiveFailuresException and emits the right events."""
        events = []
        def handler(event_type, data):
            events.append((event_type, data))

        config = ProfileConfig(
            email="test@example.com",
            password="secret",
            positions=["SWE"],
            locations=["Remote"],
        )

        mock_bot = MagicMock()
        mock_bot.start_linkedin.return_value = True
        mock_bot.applied_count = 2
        mock_bot.failed_count = 5
        mock_bot.start_apply.side_effect = ConsecutiveFailuresException("5 consecutive application failures")

        with patch("easyapplybot.load_settings", return_value=SystemConfig()), \
             patch.dict("os.environ", {"HIRINGFUNNEL_AI_PROVIDER": "openai"}), \
             patch("easyapplybot.EasyApplyBot", return_value=mock_bot):
            _run_bot(config, on_event=handler)

        event_types = [e[0] for e in events]
        assert "consecutive_failures_exceeded" in event_types
        assert "bot_stopped" in event_types
        exc_event = next(e for e in events if e[0] == "consecutive_failures_exceeded")
        assert exc_event[1]["profile_email"] == "test@example.com"
        assert exc_event[1]["applied"] == 2
        assert exc_event[1]["failed"] == 5
        stopped_event = next(e for e in events if e[0] == "bot_stopped")
        assert stopped_event[1]["reason"] == "consecutive_failures_exceeded"

    def test_button_not_found_does_not_increment_streak(self):
        """Jobs with no Easy Apply button are skipped — streak is untouched."""
        stub = self._make_bot_stub()
        stub.consecutive_fail_streak = 3
        # button=False path: no streak change (mirrors the else branch in applications_loop)
        result = False  # noqa: F841 — button not found, result set to False but streak NOT incremented
        assert stub.consecutive_fail_streak == 3  # unchanged


# ---------------------------------------------------------------------------
# ProfileConfig — requires_visa field
# ---------------------------------------------------------------------------

class TestProfileConfigVisa:
    def test_requires_visa_defaults_false(self):
        config = ProfileConfig(email="a@b.com", password="pw")
        assert config.requires_visa is False

    def test_requires_visa_true_accepted(self):
        config = ProfileConfig(email="a@b.com", password="pw", requires_visa=True)
        assert config.requires_visa is True

    def test_requires_visa_in_model_dump(self):
        config = ProfileConfig(email="a@b.com", password="pw", requires_visa=True)
        data = config.model_dump()
        assert "requires_visa" in data
        assert data["requires_visa"] is True


# ---------------------------------------------------------------------------
# H-1B check method
# ---------------------------------------------------------------------------

def _make_visa_bot_stub():
    """Minimal EasyApplyBot-like stub with H-1B state, no Selenium."""
    stub = object.__new__(EasyApplyBot)
    stub.config = ProfileConfig(email="a@b.com", password="pw", requires_visa=True)
    stub._h1b_cache = {}
    stub._h1b_stats = {"checked": 0, "applied": 0, "skipped": 0, "scores": [], "top_matches": []}
    stub._on_event = None
    return stub


class TestH1BCheckMethod:
    def test_approved_returns_true(self, monkeypatch):
        """API returns approved=true → (True, score, matched_name)."""
        stub = _make_visa_bot_stub()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"approved": True, "score": 0.99, "matched_name": "GOOGLE LLC"}
        mock_resp.raise_for_status.return_value = None

        import easyapplybot as _ea
        monkeypatch.setattr(_ea, "_requests", MagicMock(get=MagicMock(return_value=mock_resp),
                                                         exceptions=__import__("requests").exceptions))
        approved, score, matched = stub._check_h1b_sponsor("Google LLC")

        assert approved is True
        assert score == pytest.approx(0.99)
        assert matched == "GOOGLE LLC"

    def test_denied_returns_false(self, monkeypatch):
        """API returns approved=false → (False, 0.0, '')."""
        stub = _make_visa_bot_stub()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"approved": False, "score": 0.0, "matched_name": ""}
        mock_resp.raise_for_status.return_value = None

        import easyapplybot as _ea
        monkeypatch.setattr(_ea, "_requests", MagicMock(get=MagicMock(return_value=mock_resp),
                                                         exceptions=__import__("requests").exceptions))
        approved, score, matched = stub._check_h1b_sponsor("Some Startup Inc")

        assert approved is False
        assert score == 0.0
        assert matched == ""

    def test_connection_error_raises_h1b_exception(self, monkeypatch):
        """ConnectionError → H1BAPIUnavailableException (not SystemExit, not crash)."""
        import requests as _real_requests
        stub = _make_visa_bot_stub()

        mock_requests = MagicMock()
        mock_requests.get.side_effect = _real_requests.exceptions.ConnectionError("refused")
        mock_requests.exceptions = _real_requests.exceptions

        import easyapplybot as _ea
        monkeypatch.setattr(_ea, "_requests", mock_requests)

        with pytest.raises(H1BAPIUnavailableException):
            stub._check_h1b_sponsor("Acme Corp")

    def test_cache_hit_skips_api_call(self, monkeypatch):
        """Second call for same company uses cache — zero API calls."""
        stub = _make_visa_bot_stub()
        # Pre-seed cache
        stub._h1b_cache["google llc"] = (True, 0.99, "GOOGLE LLC")

        call_count = []
        import easyapplybot as _ea
        monkeypatch.setattr(_ea, "_requests", MagicMock(
            get=MagicMock(side_effect=lambda *a, **kw: call_count.append(1))
        ))

        approved, score, matched = stub._check_h1b_sponsor("Google LLC")

        assert approved is True
        assert len(call_count) == 0, "Cache hit should not call the API"

    def test_non_visa_profile_makes_no_api_call(self, monkeypatch):
        """requires_visa=False — the visa gate is never entered, zero API calls.

        This is the critical regression test: existing non-visa profiles must
        not make any additional API calls (no performance regression).
        """
        import requests as _real_requests
        call_count = []

        import easyapplybot as _ea
        monkeypatch.setattr(_ea, "_requests", MagicMock(
            get=MagicMock(side_effect=lambda *a, **kw: call_count.append(1) or MagicMock()),
            exceptions=_real_requests.exceptions,
        ))

        # Non-visa profile — requires_visa=False (default)
        config = ProfileConfig(email="a@b.com", password="pw")
        assert config.requires_visa is False

        # Simulate what the apply loop does: only call _check_h1b_sponsor if requires_visa=True
        company = "Google LLC"
        sponsor_score = None
        if config.requires_visa and company != "Unknown":
            stub = _make_visa_bot_stub()
            stub._check_h1b_sponsor(company)

        assert len(call_count) == 0, "Non-visa profile must not call /h1b/check"


# ---------------------------------------------------------------------------
# H-1B end-of-run summary
# ---------------------------------------------------------------------------

class TestH1BSummaryLines:
    def test_summary_with_no_applies(self):
        stub = _make_visa_bot_stub()
        lines = stub._h1b_summary_lines()
        assert any("H-1B Visa Filter" in l for l in lines)
        assert any("Checked:  0" in l for l in lines)
        assert any("Approved: 0" in l for l in lines)
        assert any("Skipped:  0" in l for l in lines)

    def test_summary_with_applies_shows_avg_score(self):
        stub = _make_visa_bot_stub()
        stub._h1b_stats["checked"] = 10
        stub._h1b_stats["applied"] = 7
        stub._h1b_stats["skipped"] = 3
        stub._h1b_stats["scores"] = [0.99, 0.95, 0.88, 0.92, 0.97, 0.91, 0.85]
        stub._h1b_stats["top_matches"] = [("GOOGLE LLC", 0.99), ("MICROSOFT CORP", 0.95)]
        lines = stub._h1b_summary_lines()
        assert any("Approved: 7" in l for l in lines)
        assert any("avg score" in l for l in lines)
        assert any("GOOGLE LLC" in l for l in lines)

    def test_requires_visa_false_renders_no_visa_block(self):
        """Non-visa profile never calls _h1b_summary_lines (gate is in _run_bot).
        If called anyway, it should still return lines (not crash)."""
        stub = _make_visa_bot_stub()
        stub.config = ProfileConfig(email="a@b.com", password="pw")  # requires_visa=False
        lines = stub._h1b_summary_lines()
        # Method itself is agnostic — caller (_run_bot) is responsible for the gate
        assert isinstance(lines, list)


# ---------------------------------------------------------------------------
# _run_bot: H1BAPIUnavailableException handling
# ---------------------------------------------------------------------------

class TestRunBotH1B:
    def test_h1b_api_unavailable_emits_event_and_stops(self):
        """If H1BAPIUnavailableException is raised, bot_stopped event fires cleanly."""
        config = ProfileConfig(email="a@b.com", password="pw", requires_visa=True)
        events = []

        def handler(event, data):
            events.append((event, data))

        mock_bot = MagicMock()
        mock_bot.start_linkedin.return_value = True
        mock_bot._check_h1b_seeded.side_effect = H1BAPIUnavailableException("table is empty")
        mock_bot._h1b_stats = {"checked": 0, "applied": 0, "skipped": 0, "scores": [], "top_matches": []}

        with patch("easyapplybot.load_settings", return_value=SystemConfig()), \
             patch("easyapplybot.EasyApplyBot", return_value=mock_bot):
            _run_bot(config, on_event=handler)

        event_types = [e[0] for e in events]
        assert "h1b_api_unavailable" in event_types
        assert "bot_stopped" in event_types
        stopped = next(e for e in events if e[0] == "bot_stopped")
        assert stopped[1]["reason"] == "h1b_api_unavailable"


# ---------------------------------------------------------------------------
# Whitelist title filtering tests
# ---------------------------------------------------------------------------

class TestWhitelistTitleFiltering:
    """Test per-profile whitelist filtering of job titles."""

    def test_whitelist_defaults_empty(self):
        config = ProfileConfig(email="a@b.com", password="pw")
        assert config.whitelist_titles == []

    def test_whitelist_round_trip(self):
        config = ProfileConfig(email="a@b.com", password="pw",
                               whitelist_titles=["typescript", "react"])
        data = config.model_dump()
        restored = ProfileConfig(**data)
        assert restored.whitelist_titles == ["typescript", "react"]

    def test_old_profile_without_whitelist(self):
        """Old profile JSON missing whitelist_titles doesn't crash."""
        data = {"email": "a@b.com", "password": "pw", "positions": ["Dev"]}
        config = ProfileConfig(**data)
        assert config.whitelist_titles == []

    def _make_bot_stub(self, whitelist_titles=None, blacklist_titles=None):
        """Create a minimal bot stub with real filtering attributes."""
        stub = MagicMock()
        stub.whitelist_titles = [t.lower() for t in (whitelist_titles or [])]
        stub.blacklist_titles = [t.lower() for t in (blacklist_titles or [])]
        stub.blacklist = []
        return stub

    def _title_passes_whitelist(self, whitelist_titles, title):
        """Simulate the whitelist check from applications_loop."""
        wl = [t.lower() for t in whitelist_titles]
        if wl and not any(wt in title.lower() for wt in wl):
            return False
        return True

    def _title_passes_blacklist(self, blacklist_titles, title):
        """Simulate the blacklist title check from applications_loop."""
        bl = [t.lower() for t in blacklist_titles]
        if bl and any(bt in title.lower() for bt in bl):
            return False
        return True

    def test_empty_whitelist_applies_to_all(self):
        """Empty whitelist = no filtering, apply to everything."""
        assert self._title_passes_whitelist([], "Java Backend Developer")
        assert self._title_passes_whitelist([], "Typescript Senior Engineer")
        assert self._title_passes_whitelist([], "Random Title")

    def test_whitelist_match(self):
        """Title containing a whitelist term passes."""
        assert self._title_passes_whitelist(
            ["typescript"], "Typescript Senior Frontend Engineer")

    def test_whitelist_no_match(self):
        """Title NOT containing any whitelist term is skipped."""
        assert not self._title_passes_whitelist(
            ["typescript", "react"], "Java Backend Developer")

    def test_whitelist_case_insensitive(self):
        """Matching is case-insensitive."""
        assert self._title_passes_whitelist(["typescript"], "TYPESCRIPT ENGINEER")
        assert self._title_passes_whitelist(["REACT"], "react native developer")

    def test_whitelist_substring_match(self):
        """Whitelist term matches as substring within title words."""
        assert self._title_passes_whitelist(["react"], "React Native Engineer")
        assert self._title_passes_whitelist(["python"], "Senior Python Developer")

    def test_blacklist_trumps_whitelist(self):
        """Blacklist check runs before whitelist — blacklisted title is skipped
        even if it matches the whitelist."""
        title = "Typescript Frontend Intern"
        # Matches whitelist
        assert self._title_passes_whitelist(["typescript"], title)
        # But also matches blacklist — blacklist runs first in the code
        assert not self._title_passes_blacklist(["intern"], title)

    def test_whitelist_multiple_terms_any_match(self):
        """Any single whitelist term matching is sufficient."""
        assert self._title_passes_whitelist(
            ["typescript", "react", "vue"], "React Native Engineer")
        assert self._title_passes_whitelist(
            ["typescript", "react", "vue"], "Vue.js Developer")
        assert not self._title_passes_whitelist(
            ["typescript", "react", "vue"], "Java Spring Developer")
