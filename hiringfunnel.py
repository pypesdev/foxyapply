"""HiringFunnel – TUI entry point."""

import argparse
import datetime
import logging
import logging.handlers
import os
import sys
import threading
import time
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None

from dotenv import load_dotenv
load_dotenv()

_PYPES_BASE_URL = os.environ.get("PYPES_BASE_URL", "https://api.pypes.dev")
_PYPES_API_URL = os.environ.get("PYPES_API_URL", f"{_PYPES_BASE_URL}/client/job-event")
_CLIENT_SECRET = os.environ.get("CLIENT_SECRET")


def _make_pypes_on_event(profile_name: str):
    """Returns an on_event callback that POSTs to api.pypes.dev when CLIENT_SECRET is set."""
    if not _CLIENT_SECRET or not _requests:
        return None

    def on_event(event: str, data: dict):
        if event not in ("job_applied", "job_failed", "daily_limit_reached", "consecutive_failures_exceeded"):
            return
        try:
            _requests.post(
                _PYPES_API_URL,
                json={
                    "profile": profile_name,
                    "event": event,
                    "occurred_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    **data,
                },
                headers={"X-Pypes-Secret": _CLIENT_SECRET},
                timeout=5,
            )
        except Exception:
            pass  # never crash the bot over telemetry

    return on_event

import questionary
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from boards import AVAILABLE_BOARDS, run_profile_all_boards, stop_current as stop_current_board
from db import get_all_stats, init_db, record_application
from easyapplybot import DailyLimitReachedException, EasyApplyBot, ProfileConfig, _run_bot, open_linkedin_profile
from profiles import delete_profile, list_names, load_profiles, upsert_profile
from settings import SystemConfig, load_settings, save_settings

console = Console()

# Silence noisy third-party loggers at module level
for _noisy in ("selenium", "urllib3", "WDM"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Profile form
# ---------------------------------------------------------------------------

PROFILE_FIELDS = [
    ("email", "Email address", "text"),
    ("password", "LinkedIn password", "password"),
    ("phone_number", "Phone number", "text"),
    ("positions", "Job positions (comma-separated)", "text"),
    ("remote_only", "Remote only?", "confirm"),
    ("requires_visa", "Require H-1B sponsorship? (visa mode)", "confirm"),
    ("profile_url", "LinkedIn profile URL", "text"),
    ("github_url", "GitHub profile URL (optional)", "text"),
    ("portfolio_url", "Portfolio / personal website URL (optional)", "text"),
    ("user_city", "City", "text"),
    ("user_state", "State", "text"),
    ("zip_code", "ZIP code", "text"),
    ("years_experience", "Years of experience", "text"),
    ("desired_salary", "Desired salary", "text"),
    ("job_boards", "Job boards to apply on", "checkbox", AVAILABLE_BOARDS),
]

SETTINGS_FIELDS = [
    ("ai_provider", "AI provider", "select", ["openai", "anthropic", "gemini", "ollama"]),
    ("ai_api_key", "API key for selected provider (blank for Ollama)", "text"),
    ("blacklist", "Blacklisted companies (comma-separated)", "text"),
    ("blacklist_titles", "Blacklisted job titles (comma-separated)", "text"),
]


def _parse_list(value: str) -> list:
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _prompt_single_field(field_def: tuple, current) -> tuple:
    """Prompt for a single field. Returns (cancelled: bool, value)."""
    field, label, kind = field_def[0], field_def[1], field_def[2]
    choices = field_def[3] if len(field_def) > 3 else None

    if kind == "select":
        default = current if current in choices else choices[0]
        result = questionary.select(label, choices=choices, default=default).ask()
        if result is None:
            return True, None
        return False, result

    elif kind == "confirm":
        default = bool(current) if isinstance(current, bool) else False
        result = questionary.confirm(label, default=default).ask()
        if result is None:
            return True, None
        return False, result

    elif kind == "checkbox":
        current_list = current if isinstance(current, list) else []
        qchoices = [
            questionary.Choice(c, value=c, checked=(c in current_list))
            for c in choices
        ]
        result = questionary.checkbox(label, choices=qchoices).ask()
        if result is None:
            return True, None
        return False, result

    elif kind == "password":
        result = questionary.password(label).ask()
        if result is None:
            return True, None
        return False, result if result else current

    else:
        display = current
        if isinstance(display, list):
            display = ", ".join(display)
        elif isinstance(display, int):
            display = str(display) if display else ""
        result = questionary.text(label, default=str(display)).ask()
        if result is None:
            return True, None
        if field in ("positions", "blacklist", "blacklist_titles"):
            return False, _parse_list(result)
        elif field in ("years_experience", "desired_salary"):
            return False, _parse_int(result)
        else:
            return False, result


def _field_choice_label(field_def: tuple, data: dict) -> str:
    """Format a field picker label showing the current value."""
    field, label, kind = field_def[0], field_def[1], field_def[2]
    val = data.get(field, "")
    if kind == "password":
        display = "••••••••" if val else "(not set)"
    elif kind == "confirm":
        display = "Yes" if val else "No"
    elif isinstance(val, list):
        display = ", ".join(val) if val else "(empty)"
    elif val == "" or val is None:
        display = "(not set)"
    else:
        display = str(val)
        if len(display) > 40:
            display = display[:37] + "..."
    return f"{label}: {display}"


def prompt_profile(existing: Optional[dict] = None) -> Optional[dict]:
    """Prompt for all profile fields. Returns data dict or None if cancelled."""
    data = existing or {}
    answers = {}

    for field_def in PROFILE_FIELDS:
        cancelled, value = _prompt_single_field(field_def, data.get(field_def[0], ""))
        if cancelled:
            return None
        answers[field_def[0]] = value

    city = answers.get("user_city", "").strip()
    state = answers.get("user_state", "").strip()
    if city and state:
        answers["locations"] = [f"{city}, {state}"]
    elif city:
        answers["locations"] = [city]
    elif state:
        answers["locations"] = [state]
    else:
        answers["locations"] = []

    return answers


def _open_linkedin_action(data: dict) -> None:
    """Open a browser, log in to LinkedIn, and navigate to the profile URL."""
    email = data.get("email", "")
    password = data.get("password", "")
    if not email or not password:
        console.print("[yellow]Set email and password first before opening LinkedIn.[/yellow]")
        return
    try:
        cfg = ProfileConfig(**data)
    except Exception as e:
        console.print(f"[red]Profile config error: {e}[/red]")
        return

    done = threading.Event()
    result_box: list = []

    def _run(cfg=cfg):
        result_box.append(open_linkedin_profile(cfg))
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    with console.status("[cyan]Opening browser and logging in to LinkedIn...[/cyan]"):
        done.wait()

    if result_box and result_box[0]:
        console.print("[green]Browser opened — LinkedIn is loaded. The window stays open.[/green]")
    else:
        console.print("[red]Failed to log in to LinkedIn. Check your email and password.[/red]")


def prompt_profile_edit(existing: dict) -> Optional[dict]:
    """Edit individual profile fields via a picker loop. Returns updated dict or None if cancelled."""
    data = dict(existing)

    while True:
        field_choices = [
            questionary.Choice(_field_choice_label(fd, data), value=i)
            for i, fd in enumerate(PROFILE_FIELDS)
        ]
        field_choices.append(questionary.Choice("Open LinkedIn profile in browser", value="open_linkedin"))
        field_choices.append(questionary.Separator())
        field_choices.append(questionary.Choice("Save & exit", value="save"))
        field_choices.append(questionary.Choice("Cancel", value="cancel"))

        action = questionary.select("Select field to edit:", choices=field_choices).ask()

        if action is None or action == "cancel":
            return None
        if action == "open_linkedin":
            _open_linkedin_action(data)
            continue
        if action == "save":
            city = data.get("user_city", "").strip()
            state = data.get("user_state", "").strip()
            if city and state:
                data["locations"] = [f"{city}, {state}"]
            elif city:
                data["locations"] = [city]
            elif state:
                data["locations"] = [state]
            else:
                data["locations"] = []
            return data

        field_def = PROFILE_FIELDS[action]
        cancelled, value = _prompt_single_field(field_def, data.get(field_def[0], ""))
        if not cancelled:
            data[field_def[0]] = value


def prompt_settings_edit(current: dict) -> Optional[dict]:
    """Prompt for each system setting in sequence. Returns updated dict or None if cancelled."""
    data = dict(current)
    for fd in SETTINGS_FIELDS:
        cancelled, value = _prompt_single_field(fd, data.get(fd[0], ""))
        if cancelled:
            return None
        data[fd[0]] = value
    return data


# ---------------------------------------------------------------------------
# Run panel
# ---------------------------------------------------------------------------

class BotState:
    def __init__(self, profile_name: str, requires_visa: bool = False):
        self.profile_name = profile_name
        self.applied = 0
        self.failed = 0
        self.seen = 0
        self.status = "Starting..."
        self.current_board = ""   # e.g. "LinkedIn", "Indeed"
        self.log_lines: list = []
        self.stopped = False
        self.daily_limit_hit = False
        self.requires_visa = requires_visa
        self.h1b_skipped = 0
        self.h1b_summary_lines: list = []   # populated by h1b_session_summary event

    def on_event(self, event_type: str, data: dict) -> None:
        if event_type == "board_started":
            self.current_board = data.get("display", data.get("board", ""))
            self.status = f"[{self.current_board}] Starting..."
        elif event_type == "board_finished":
            board = data.get("display", data.get("board", ""))
            result = data.get("result", "")
            if result == "daily_limit":
                self.log_lines.append(f"  [{board}] Daily limit reached")
            elif result == "not_implemented":
                self.log_lines.append(f"  [{board}] Not yet implemented — see boards/{data.get('board','')}.py")
            elif result == "error":
                self.log_lines.append(f"  [{board}] Error — check logs")
            else:
                self.log_lines.append(f"  [{board}] Done")
        elif event_type == "bot_started":
            self.requires_visa = data.get("requires_visa", False)
            self.status = f"[{self.current_board}] Applying to jobs..."
        elif event_type == "bot_stopped":
            reason = data.get("reason", "")
            self.status = f"Stopped: {reason}"
            self.stopped = True
        elif event_type == "login_manual_required":
            msg = data.get("message", "Please log in manually in the browser.")
            self.status = f"[{self.current_board}] Waiting for manual login..."
            self.log_lines.append(f"  [yellow]{msg}[/yellow]")
        elif event_type == "2fa_required":
            self.status = f"[{self.current_board}] 2FA required — enter code in the browser"
            self.log_lines.append("  [yellow]2FA/verification detected — complete it in the browser window[/yellow]")
        elif event_type == "login_success":
            self.status = f"[{self.current_board}] Logged in. Searching..."
        elif event_type == "login_failed":
            self.status = f"[{self.current_board}] Login failed: {data.get('error', '')}"
            self.stopped = True
        elif event_type == "job_applying":
            title = data.get("title", "")
            company = data.get("company", "")
            self.status = f"Applying: {title} @ {company}"
            self.log_lines.append(f"  Applying: {title} @ {company}")
        elif event_type == "job_applied":
            title = data.get("title", "")
            company = data.get("company", "")
            self.applied += 1
            self.log_lines.append(f"  [green]Applied[/green]: {title}")
            try:
                record_application(self.profile_name, data.get("job_id", ""), title, company, "applied")
            except Exception:
                pass
        elif event_type == "job_failed":
            title = data.get("title", "")
            self.failed += 1
            self.log_lines.append(f"  [red]Failed[/red]: {title}")
            try:
                record_application(self.profile_name, data.get("job_id", ""), title, data.get("company", ""), "failed")
            except Exception:
                pass
        elif event_type == "progress":
            self.applied = data.get("applied", self.applied)
            self.failed = data.get("failed", self.failed)
            self.seen = data.get("total_seen", self.seen)
        elif event_type == "daily_limit_reached":
            self.daily_limit_hit = True
            email = data.get("profile_email", "this profile")
            self.status = f"Daily limit reached for {email}"
            self.log_lines.append(f"  [yellow]Daily limit reached[/yellow] for {email}")
        elif event_type == "consecutive_failures_exceeded":
            email = data.get("profile_email", "this profile")
            self.status = f"Consecutive failure limit hit for {email}"
            self.log_lines.append(f"  [red]5 consecutive failures[/red] for {email}, moving on")
        elif event_type == "h1b_skipped":
            self.h1b_skipped += 1
        elif event_type == "h1b_api_unavailable":
            msg = data.get("message", "")
            self.status = "[red]H-1B API unavailable — run aborted[/red]"
            self.log_lines.append(f"  [red][H-1B ABORT][/red] {msg}")
            self.stopped = True
        elif event_type == "h1b_session_summary":
            self.h1b_summary_lines = data.get("lines", [])
        elif event_type == "error":
            msg = data.get("message", "")
            self.log_lines.append(f"  [red]Error[/red]: {msg}")

        # Keep log buffer trimmed
        if len(self.log_lines) > 20:
            self.log_lines = self.log_lines[-20:]

    def render(self) -> Panel:
        board_tag = f"  [dim]({self.current_board})[/dim]" if self.current_board else ""
        visa_badge = "  [yellow][H-1B mode ON][/yellow]" if self.requires_visa else ""
        header = (
            f"Profile: [bold]{self.profile_name}[/bold]{board_tag}{visa_badge}\n"
            f"Applied: [green]{self.applied}[/green]  "
            f"Failed: [red]{self.failed}[/red]  "
            f"Seen: {self.seen}\n"
        )
        if self.requires_visa:
            header += f"Skipped (no H-1B): [yellow]{self.h1b_skipped}[/yellow]\n"
        header += f"Status: {self.status}"
        log_text = "\n".join(self.log_lines[-10:]) if self.log_lines else ""
        body = header + ("\n\n" + log_text if log_text else "")
        return Panel(body, title="[bold blue]HiringFunnel[/bold blue]", expand=False)


def _redirect_logs_to_file() -> None:
    """Route all log output to a file so nothing bleeds into the TUI."""
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        "logs/hiringfunnel.log", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s", "%H:%M:%S")
    )

    # Strip StreamHandlers from root so basicConfig() won't add another one
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            root.removeHandler(h)
    root.addHandler(file_handler)

    # Pre-populate the easyapplybot logger so setup_logger()'s
    # `if not log.handlers` guard skips adding a StreamHandler
    bot_log = logging.getLogger("easyapplybot")
    for h in list(bot_log.handlers):
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            bot_log.removeHandler(h)
    bot_log.addHandler(file_handler)
    bot_log.setLevel(logging.DEBUG)
    bot_log.propagate = False


def run_profile_sequence(start_name: str, all_names: list, profiles: dict) -> None:
    """Run every profile in sequence.

    For each profile all configured job boards run in order before moving to
    the next profile:  LinkedIn → Indeed → [more boards] → next profile.
    """
    remaining = [n for n in all_names if n != start_name]
    names_to_try = [start_name] + remaining

    _redirect_logs_to_file()
    stop_all = threading.Event()

    for name in names_to_try:
        if stop_all.is_set():
            break

        data = profiles.get(name, {})
        try:
            config = ProfileConfig(**data)
        except Exception as e:
            console.print(f"[red]Invalid profile '{name}': {e}[/red]")
            continue

        boards_label = ", ".join(config.job_boards) if config.job_boards else "none"
        console.print(
            f"\nRunning profile [bold]{name}[/bold] "
            f"[dim]({boards_label})[/dim]. "
            f"Press [bold]Ctrl+C[/bold] to stop.\n"
        )

        state = BotState(name, requires_visa=config.requires_visa)
        bot_done = threading.Event()
        pypes_handler = _make_pypes_on_event(name)

        def _combined_on_event(event: str, data: dict, st=state, ph=pypes_handler):
            st.on_event(event, data)
            if ph:
                ph(event, data)

        def bot_thread_fn(cfg=config, done=bot_done):
            run_profile_all_boards(cfg, on_event=_combined_on_event)
            done.set()

        thread = threading.Thread(target=bot_thread_fn, daemon=True)
        thread.start()

        try:
            with Live(state.render(), refresh_per_second=2, console=console) as live:
                while not state.stopped and not bot_done.is_set():
                    live.update(state.render())
                    time.sleep(0.5)
                live.update(state.render())
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping bot...[/yellow]")
            stop_current_board()          # signal active board bot
            from easyapplybot import _bot  # also stop LinkedIn bot if running
            if _bot is not None:
                _bot.stop()
            thread.join(timeout=15)
            stop_all.set()
            break

        thread.join(timeout=15)

        # Print H-1B end-of-run summary if visa mode was active.
        if state.requires_visa and state.h1b_summary_lines:
            for line in state.h1b_summary_lines:
                console.print(line)

    console.print("[green]All profiles completed.[/green]")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def build_menu_choices(names: list, stats: dict = {}) -> list:
    choices = []
    for name in names:
        n_applied = stats.get(name, {}).get("applied", 0)
        choices.append(questionary.Choice(f'Run: "{name}"  (applied: {n_applied})', value=("run", name)))
    if names:
        choices.append(questionary.Separator())
    choices.append(questionary.Choice("Create new profile", value=("create", None)))
    choices.append(questionary.Choice("Edit a profile", value=("edit", None)))
    choices.append(questionary.Choice("Delete a profile", value=("delete", None)))
    choices.append(questionary.Separator())
    choices.append(questionary.Choice("Settings", value=("settings", None)))
    choices.append(questionary.Choice("Quit", value=("quit", None)))
    return choices


def main() -> None:
    parser = argparse.ArgumentParser(prog="hiringfunnel", add_help=False)
    parser.add_argument("--run", metavar="PROFILE", default=None,
                        help="Run a profile non-interactively (no TUI)")
    parser.add_argument("--headless", action="store_true",
                        help="Launch Chrome in headless mode (use with --run)")
    args, _ = parser.parse_known_args()

    if args.headless:
        os.environ["HIRINGFUNNEL_HEADLESS"] = "1"

    if args.run:
        profiles = load_profiles()
        names = list_names()
        if args.run not in profiles:
            console.print(
                f"[red]Profile '{args.run}' not found. "
                f"Available: {', '.join(names) or 'none'}[/red]"
            )
            sys.exit(1)
        init_db()
        _redirect_logs_to_file()
        run_profile_sequence(args.run, names, profiles)
        return

    console.print("[bold blue]HiringFunnel[/bold blue] – LinkedIn Easy Apply Bot\n")

    init_db()

    while True:
        names = list_names()
        stats = get_all_stats()
        choices = build_menu_choices(names, stats)

        answer = questionary.select(
            "What would you like to do?",
            choices=choices,
        ).ask()

        if answer is None or answer == ("quit", None):
            console.print("Goodbye.")
            break

        action, target = answer

        if action == "run":
            profiles = load_profiles()
            run_profile_sequence(target, names, profiles)

        elif action == "create":
            name = questionary.text("Profile name:").ask()
            if not name:
                continue
            profiles = load_profiles()
            if name in profiles:
                console.print(f"[yellow]Profile '{name}' already exists. Use Edit to modify it.[/yellow]")
                continue
            data = prompt_profile()
            if data is None:
                continue
            upsert_profile(name, data)
            console.print(f"[green]Profile '{name}' created.[/green]")

        elif action == "edit":
            if not names:
                console.print("[yellow]No profiles to edit.[/yellow]")
                continue
            name = questionary.select(
                "Select profile to edit:",
                choices=names,
            ).ask()
            if not name:
                continue
            profiles = load_profiles()
            data = prompt_profile_edit(profiles.get(name, {}))
            if data is None:
                continue
            upsert_profile(name, data)
            console.print(f"[green]Profile '{name}' updated.[/green]")

        elif action == "delete":
            if not names:
                console.print("[yellow]No profiles to delete.[/yellow]")
                continue
            name = questionary.select(
                "Select profile to delete:",
                choices=names,
            ).ask()
            if not name:
                continue
            confirmed = questionary.confirm(f"Delete profile '{name}'?", default=False).ask()
            if confirmed:
                delete_profile(name)
                console.print(f"[green]Profile '{name}' deleted.[/green]")

        elif action == "settings":
            current = load_settings()
            result = prompt_settings_edit(current.model_dump())
            if result is None:
                continue
            save_settings(SystemConfig(**result))
            console.print("[green]Settings saved.[/green]")


if __name__ == "__main__":
    main()
