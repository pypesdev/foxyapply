import datetime
import hashlib
import logging
import os
import pickle
import random
import re
import threading
import time
from typing import Callable, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, model_validator

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
try:
    import undetected_chromedriver as uc
except ImportError:
    uc = None  # type: ignore[assignment]
try:
    import pyautogui
except ImportError:
    pyautogui = None  # type: ignore[assignment]

try:
    import anthropic as _anthropic
except ImportError:
    _anthropic = None  # type: ignore[assignment]

try:
    from google import genai as _genai
except ImportError:
    _genai = None  # type: ignore[assignment]

try:
    import ollama as _ollama
except ImportError:
    _ollama = None  # type: ignore[assignment]

from fake_useragent import UserAgent
from openai import OpenAI
from dotenv import load_dotenv

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

from settings import _inject_ai_env, load_settings

load_dotenv()  # load .env regardless of entry point (hiringfunnel.py, run_profiles_batch.py, etc.)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class DailyLimitReachedException(Exception):
    """Raised when LinkedIn's daily Easy Apply submission limit is detected on page."""
    pass


class ConsecutiveFailuresException(Exception):
    """Raised when the bot fails to apply to MAX_CONSECUTIVE_FAILURES jobs in a row."""
    pass


class H1BAPIUnavailableException(Exception):
    """Raised when the pypes H-1B check API is unreachable during a visa-mode run.

    The bot aborts on this exception rather than silently applying to all companies,
    because falling back to unrestricted applications defeats the visa-filter guarantee.
    """
    pass


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------

class ProfileConfig(BaseModel):
    email: str
    password: str
    phone_number: str = ""
    positions: List[str] = []
    locations: List[str] = []
    remote_only: bool = False
    profile_url: str = ""
    user_city: str = ""
    user_state: str = ""
    zip_code: str = ""
    years_experience: int = 0
    desired_salary: int = 0
    github_url: str = ""
    portfolio_url: str = ""
    job_boards: List[str] = ["linkedin"]
    # H-1B visa filter: when True the bot only applies to companies with a
    # documented H-1B sponsorship record (via GET /h1b/check on the pypes API).
    # PYPES_BASE_URL env var controls the API base (default: https://api.pypes.dev).
    requires_visa: bool = False
    # Per-profile whitelist: when non-empty, only apply to jobs whose title
    # contains at least one of these terms (case-insensitive substring match).
    # Empty list = disabled (apply to everything).
    whitelist_titles: List[str] = []

    @model_validator(mode='before')
    @classmethod
    def _migrate_legacy(cls, data):
        if isinstance(data, dict):
            # openai_api_key → ai_api_key (old field name)
            if 'openai_api_key' in data and 'ai_api_key' not in data:
                data['ai_api_key'] = data.pop('openai_api_key')
                data.setdefault('ai_provider', 'openai')
            # ai_provider + ai_api_key moved to system settings (settings.json)
            data.pop('ai_provider', None)
            data.pop('ai_api_key', None)
            # blacklist + blacklist_titles moved to system settings (settings.json)
            data.pop('blacklist', None)
            data.pop('blacklist_titles', None)
        return data


# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------

def setup_logger() -> None:
    log_dir = os.path.join('.', 'logs')
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s',
        datefmt='%d-%b-%y %H:%M:%S',
    )
    log.setLevel(logging.DEBUG)
    if not log.handlers:
        c_handler = logging.StreamHandler()
        c_handler.setLevel(logging.DEBUG)
        c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
        c_handler.setFormatter(c_format)
        log.addHandler(c_handler)


# ---------------------------------------------------------------------------
# Chrome driver factory
# ---------------------------------------------------------------------------

def _make_chrome_driver():
    ua = UserAgent()
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-blink-features")
    options.add_argument(f'--user-agent={ua.random}')
    options.add_argument('--disable-blink-features=AutomationControlled')
    if os.environ.get("HIRINGFUNNEL_HEADLESS") == "1":
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
    if uc is not None:
        # Detect installed Chrome major version to avoid driver/browser mismatch
        chrome_ver = None
        try:
            import subprocess
            out = subprocess.check_output(
                ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
                stderr=subprocess.DEVNULL, text=True)
            chrome_ver = int(out.strip().split()[-1].split(".")[0])
            log.info(f"Starting Chrome via undetected-chromedriver (Chrome {chrome_ver})")
        except Exception:
            log.info("Starting Chrome via undetected-chromedriver")
        driver = uc.Chrome(options=options, version_main=chrome_ver)
    else:
        log.info("Starting Chrome via standard Selenium (undetected-chromedriver not installed)")
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass
    driver.set_page_load_timeout(30)
    return driver


# ---------------------------------------------------------------------------
# EasyApplyBot
# ---------------------------------------------------------------------------

class EasyApplyBot:
    MAX_SEARCH_TIME = 20 * 60 * 60
    MAX_CONSECUTIVE_FAILURES = 5

    def __init__(self, config: ProfileConfig, on_event: Optional[Callable[[str, dict], None]] = None,
                 blacklist: Optional[List[str]] = None, blacklist_titles: Optional[List[str]] = None) -> None:
        setup_logger()

        self._on_event = on_event

        log.info("Welcome to Easy Apply Bot")

        self._stop_event = threading.Event()
        self.applied_count = 0
        self.failed_count = 0
        self.total_seen = 0
        self.consecutive_fail_streak = 0

        self.config = config
        self.phone_number = config.phone_number
        self.location = f"{config.user_city}, {config.user_state}" if config.user_city else ""
        self.years_of_experience = str(config.years_experience) if config.years_experience else ""
        self.desired_salary = str(config.desired_salary) if config.desired_salary else ""
        self.linkedin_profile_url = config.profile_url
        self.github_url = config.github_url
        self.portfolio_url = config.portfolio_url
        self.zip_code = config.zip_code
        self.user_state = config.user_state
        self.checked_invalid = False
        self.blacklist = [c.lower() for c in (blacklist or [])]
        self.blacklist_titles = [t.lower() for t in (blacklist_titles or [])]
        self.whitelist_titles = [t.lower() for t in config.whitelist_titles]

        # H-1B visa filter state (only active when config.requires_visa=True).
        # _h1b_cache: per-session company lookup cache keyed by lowercase company name.
        #   Value: (approved: bool, score: float, matched_name: str)
        # _h1b_stats: counters accumulated during the session; printed in end-of-run summary.
        self._h1b_cache: dict = {}
        self._h1b_stats = {
            "checked": 0,
            "applied": 0,
            "skipped": 0,
            "scores": [],       # sponsor_score for each approved company applied to
            "top_matches": [],  # (matched_name, score) for end-of-run summary
        }

        # Setup Selenium driver
        self.browser = self._create_driver()
        self.wait = WebDriverWait(self.browser, 30)

    def _emit(self, event_type: str, data: Optional[dict] = None) -> None:
        """Call the on_event callback if set."""
        if self._on_event is not None:
            try:
                self._on_event(event_type, data or {})
            except Exception as e:
                log.debug(f"on_event callback error: {e}")

    # -----------------------------------------------------------------------
    # H-1B visa filter
    # -----------------------------------------------------------------------

    def _check_h1b_seeded(self) -> None:
        """Verify the H-1B employer table is populated before starting a visa-mode run.

        Calls GET /h1b/health. Raises H1BAPIUnavailableException if:
          - the API is unreachable
          - employer_count == 0 (seed-h1b.ts was never run)

        This guard prevents the silent failure where an empty table causes every
        company to return approved=False, skipping 100% of jobs with no warning.
        """
        if _requests is None:
            raise H1BAPIUnavailableException("'requests' library is not installed — cannot use visa mode")

        base = os.environ.get("PYPES_BASE_URL", "https://api.pypes.dev")
        secret = os.environ.get("CLIENT_SECRET", "")
        headers = {"X-Pypes-Secret": secret} if secret else {}

        try:
            resp = _requests.get(f"{base}/h1b/health", headers=headers, timeout=5)
            resp.raise_for_status()
        except Exception as e:
            raise H1BAPIUnavailableException(
                f"[H-1B] Cannot reach pypes API at {base}: {e}\n"
                f"Check PYPES_BASE_URL and CLIENT_SECRET env vars."
            )

        count = resp.json().get("employer_count", 0)
        if count == 0:
            raise H1BAPIUnavailableException(
                "[H-1B] h1b_employers table is empty — run: bun run seed:h1b\n"
                "Without H-1B data, visa-mode would silently skip every company."
            )
        log.info(f"[H-1B] Employer table verified: {count:,} rows loaded")

    def _check_h1b_sponsor(self, company: str) -> tuple:
        """Check if a company has an H-1B sponsorship record via the pypes API.

        Returns (approved: bool, score: float, matched_name: str).

        Uses an in-session cache keyed by lowercased company name to avoid
        duplicate API calls when the same employer appears in multiple listings.

        Raises H1BAPIUnavailableException on connection errors or non-2xx responses.
        The bot aborts on this exception — do NOT silently fall back to applying
        to all companies, as that defeats the visa-filter safety guarantee.
        """
        key = company.lower().strip()

        if key in self._h1b_cache:
            return self._h1b_cache[key]

        base = os.environ.get("PYPES_BASE_URL", "https://api.pypes.dev")
        secret = os.environ.get("CLIENT_SECRET", "")
        headers = {"X-Pypes-Secret": secret} if secret else {}

        try:
            resp = _requests.get(
                f"{base}/h1b/check",
                params={"company": company},
                headers=headers,
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            result = (data.get("approved", False), data.get("score", 0.0), data.get("matched_name", ""))
        except _requests.exceptions.ConnectionError as e:
            raise H1BAPIUnavailableException(
                f"[H-1B] Cannot reach pypes API at {base}: {e}"
            )
        except Exception as e:
            raise H1BAPIUnavailableException(
                f"[H-1B] API error for {company!r}: {e}"
            )

        self._h1b_cache[key] = result
        return result

    def _h1b_summary_lines(self) -> list:
        """Return the end-of-run H-1B visa filter summary as a list of lines."""
        s = self._h1b_stats
        lines = [
            "",
            "=== H-1B Visa Filter ===",
            f"Checked:  {s['checked']} companies",
            f"Approved: {s['applied']}  (avg score: {sum(s['scores']) / len(s['scores']):.2f})" if s['scores'] else f"Approved: {s['applied']}",
            f"Skipped:  {s['skipped']}  (no USCIS record or score < 0.4)",
        ]
        if s["top_matches"]:
            lines.append("")
            lines.append("Top sponsors applied to:")
            for name, score in sorted(s["top_matches"], key=lambda x: -x[1])[:5]:
                lines.append(f"  {name:<30} {score:.2f}")
        return lines

    # -----------------------------------------------------------------------

    def _check_daily_limit(self) -> bool:
        """Return True if LinkedIn's daily submission limit notice is present."""
        try:
            elements = self.browser.find_elements(By.CLASS_NAME, "artdeco-inline-feedback__message")
            if any("limit daily submissions" in el.text.lower() for el in elements):
                return True
            # Modal dialog: "You reached today's Easy Apply limit"
            dialogs = self.browser.find_elements(
                By.CSS_SELECTOR, '[data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.EasyApplyFuseLimitDialogModal"]')
            if dialogs:
                return True
            return False
        except Exception:
            return False

    def _create_driver(self):
        return _make_chrome_driver()

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def stop(self):
        self._stop_event.set()

    @property
    def stopped(self):
        return self._stop_event.is_set()

    def close(self):
        try:
            self.browser.quit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # LinkedIn login
    # ------------------------------------------------------------------

    def _is_logged_in(self) -> bool:
        """Return True if the current page indicates a logged-in LinkedIn session."""
        url = self.browser.current_url
        # Logged-in pages: /feed, /jobs, /mynetwork, or the base linkedin.com
        # homepage (which only shows when authenticated — unauthenticated users
        # get redirected to /login or /authwall).
        if "/feed" in url or "/jobs" in url or "/mynetwork" in url:
            return True
        if "/login" in url or "/authwall" in url or "/checkpoint" in url:
            return False
        # Check for the global nav element that only renders when logged in
        try:
            self.browser.find_element(By.ID, "global-nav")
            return True
        except Exception:
            pass
        # Fallback: on linkedin.com with no login/authwall path means we're
        # authenticated (e.g. https://www.linkedin.com/ after cookie restore)
        parsed = urlparse(url)
        if parsed.hostname and "linkedin.com" in parsed.hostname:
            path = parsed.path.rstrip("/")
            if path == "" or path in ("/feed", "/jobs", "/mynetwork", "/messaging"):
                return True
        return False

    # ------------------------------------------------------------------
    # Cookie persistence (per-email)
    # ------------------------------------------------------------------

    def _cookie_path(self, email: str) -> str:
        """Return the cookie file path for the given email."""
        slug = hashlib.sha256(email.lower().strip().encode()).hexdigest()[:12]
        return os.path.expanduser(f"~/.hiringfunnel/linkedin_session_{slug}.pkl")

    def _try_cookie_login(self, email: str) -> bool:
        """Load saved cookies and check if the LinkedIn session is still valid."""
        path = self._cookie_path(email)
        if not os.path.exists(path):
            return False
        try:
            self.browser.get("https://www.linkedin.com")
            time.sleep(1)
            with open(path, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                try:
                    self.browser.add_cookie(cookie)
                except Exception:
                    pass
            self.browser.refresh()
            time.sleep(2)
            if self._is_logged_in():
                return True
            # Session expired — delete stale cookies and fall through
            log.info("Saved LinkedIn session expired, falling back to login")
            self._emit("cookie_login_expired")
            os.remove(path)
            return False
        except Exception as e:
            log.warning(f"Cookie login failed: {e}")
            # Remove corrupted cookie file
            try:
                os.remove(path)
            except OSError:
                pass
            return False

    def _save_cookies(self, email: str) -> None:
        """Persist current browser cookies to disk for next run."""
        path = self._cookie_path(email)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                pickle.dump(self.browser.get_cookies(), f)
            log.info("LinkedIn cookies saved for next run")
        except Exception as e:
            log.warning(f"Could not save cookies: {e}")

    # ------------------------------------------------------------------

    def _handle_welcome_back(self, email: str) -> bool:
        """Handle LinkedIn's 'Welcome Back' page that lists saved profiles.

        If the user's email domain matches a listed profile, click it.
        If not, click 'Sign in using another account' to get the standard form.
        Returns True if a matching profile was clicked, False if the page
        wasn't a Welcome Back page or no match was found.
        """
        try:
            profile_buttons = self.browser.find_elements(
                By.CSS_SELECTOR, "button.member-profile__details"
            )
        except Exception:
            return False

        if not profile_buttons:
            return False

        log.info("Welcome Back page detected with %d saved profile(s)", len(profile_buttons))

        # LinkedIn masks emails like "a*****@domain.com" — match on domain
        email_domain = email.lower().strip().split("@", 1)[1] if "@" in email else ""
        for btn in profile_buttons:
            try:
                handle = btn.find_element(By.CSS_SELECTOR, "p.profile__handle").text
                if handle and "@" in handle:
                    handle_domain = handle.lower().strip().split("@", 1)[1]
                    if handle_domain == email_domain:
                        log.info("Clicking matching saved profile: %s", handle)
                        btn.click()
                        return True
            except Exception:
                continue

        # No matching profile — click "Sign in using another account"
        try:
            other_btn = self.browser.find_element(
                By.CSS_SELECTOR, "button.signin-other-account"
            )
            log.info("No matching saved profile — clicking 'Sign in using another account'")
            other_btn.click()
            time.sleep(2)
        except Exception:
            log.warning("Could not find 'Sign in using another account' button")
        return False

    def start_linkedin(self, username, password) -> bool:
        # Try saved cookies first
        #_login(username):
            # log.info("Logged in via saved cookies")
            # self._emit("login_success")
            # return True

        log.info("Logging in.....Please wait :)")
        self.browser.get("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
        time.sleep(2)

        # Handle "Welcome Back" page — click matching profile or
        # "Sign in using another account" to get the standard login form.
        # Clicking a profile does NOT authenticate; it just pre-selects the
        # account. Always fall through to the password form.
        self._handle_welcome_back(username)
        time.sleep(2)

        try:
            user_field = self.browser.find_element("id", "username")
            pw_field = self.browser.find_element("id", "password")
            login_button = self.browser.find_element(By.CLASS_NAME, "btn__primary--large")
            user_field.send_keys(username)
            user_field.send_keys(Keys.TAB)
            time.sleep(2)
            pw_field.send_keys(password)
            time.sleep(2)
            login_button.click()
            time.sleep(3)

            # Check for 2FA / verification challenge
            if not self._is_logged_in():
                log.info("2FA or verification challenge detected — waiting for manual input")
                self._emit("2fa_required")
                # Poll until logged in or stopped, up to 5 minutes
                deadline = time.time() + 300
                while not self._is_logged_in() and not self.stopped:
                    if time.time() > deadline:
                        log.info("Timed out waiting for 2FA")
                        self._emit("login_failed", {"error": "2FA timeout"})
                        return False
                    time.sleep(3)

            self._save_cookies(username)
            self._emit("login_success")
            return True
        except TimeoutException:
            log.info("TimeoutException! Username/password field or login button not found")
            self._emit("login_failed", {"error": "Timeout finding login fields"})
            return False
        except Exception as e:
            self._emit("login_failed", {"error": str(e)})
            return False

    # ------------------------------------------------------------------
    # Main apply loop
    # ------------------------------------------------------------------

    def fill_data(self) -> None:
        pass

    def start_apply(self, positions, locations) -> None:
        self.fill_data()

        combos = []
        while len(combos) < len(positions) * len(locations):
            if self.stopped:
                return
            position = positions[random.randint(0, len(positions) - 1)]
            location = locations[random.randint(0, len(locations) - 1)]
            combo = (position, location)
            if combo not in combos:
                combos.append(combo)
                log.info(f"Applying to {position}: {location}")
                location_param = "&location=" + location
                self.applications_loop(position, location_param)
            if len(combos) > 500:
                break

    def applications_loop(self, position, location):
        count_application = 0
        jobs_per_page = 0
        start_time = time.time()

        log.info("Looking for jobs.. Please wait..")
        try:
            self.browser.set_window_position(1, 1)
            self.browser.maximize_window()
        except Exception as e:
            log.info(f"Could not set window size/position: {e}")

        self.browser, _ = self.next_jobs_page(position, location, jobs_per_page)
        log.info("Looking for jobs.. Please wait..")

        while time.time() - start_time < self.MAX_SEARCH_TIME:
            if self.stopped:
                return

            try:
                log.info(f"{(self.MAX_SEARCH_TIME - (time.time() - start_time)) // 60} minutes left in this search")

                self.load_page()
                links = self.browser.find_elements("xpath", '//div[@data-job-id]')
                if len(links) == 0:
                    log.debug("No links found")
                    break

                IDs = []
                for link in links:
                    children = link.find_elements("xpath", './/a[contains(@class, "job-card-container__link")]')
                    for child in children:
                        href = child.get_attribute("href")
                        if href:
                            parsed_url = urlparse(href)
                            job_id = parsed_url.path.split('/')[-2]
                            if job_id:
                                try:
                                    IDs.append(int(job_id))
                                except ValueError:
                                    pass
                jobIDs = set(IDs)
                self.total_seen += len(jobIDs)

                for jobID in jobIDs:
                    if self.stopped:
                        return

                    if self.get_job_page(jobID) is None:
                        continue

                    # Extract title/company for events
                    try:
                        title_parts = self.browser.title.split(' | ')
                        job_title = re.search(r"\(?\d?\)?\s?(\w.*)", title_parts[0])
                        job_title = job_title.group(1) if job_title else title_parts[0]
                        company = re.search(r"(\w.*)", title_parts[1]) if len(title_parts) > 1 else None
                        company = company.group(1) if company else "Unknown"
                    except Exception:
                        job_title = "Unknown"
                        company = "Unknown"

                    # Check blacklists
                    if self.blacklist and any(bc in company.lower() for bc in self.blacklist):
                        log.info(f"Skipping blacklisted company: {company}")
                        continue
                    if self.blacklist_titles and any(bt in job_title.lower() for bt in self.blacklist_titles):
                        log.info(f"Skipping blacklisted title: {job_title}")
                        continue

                    # Whitelist filter: if whitelist is set, only apply to matching titles
                    if self.whitelist_titles and not any(wt in job_title.lower() for wt in self.whitelist_titles):
                        log.info(f"Skipping non-whitelisted title: {job_title}")
                        continue

                    # H-1B visa filter: skip companies with no USCIS sponsorship record.
                    # Only active when requires_visa=True. Raises H1BAPIUnavailableException
                    # on connectivity failure — the outer loop propagates it to abort the run.
                    sponsor_score: Optional[float] = None
                    sponsor_matched_name: str = ""
                    if self.config.requires_visa and company != "Unknown":
                        approved, score, matched = self._check_h1b_sponsor(company)
                        self._h1b_stats["checked"] += 1
                        if not approved:
                            self._h1b_stats["skipped"] += 1
                            log.info(f"[H-1B SKIP] {company} — no sponsorship record")
                            self._emit("h1b_skipped", {"company": company})
                            continue
                        self._h1b_stats["applied"] += 1
                        self._h1b_stats["scores"].append(score)
                        self._h1b_stats["top_matches"].append((matched, score))
                        sponsor_score = score
                        sponsor_matched_name = matched
                        log.info(f"[H-1B OK] {company} → {matched} (score={score:.2f})")

                    self._emit("job_applying", {"job_id": str(jobID), "title": job_title, "company": company})

                    button = self.get_easy_apply_button()

                    if button is not False:
                        log.info("Clicking the EASY apply button")
                        time.sleep(3)
                        try:
                            result = self.send_resume(deadline=time.time() + 600)
                            count_application += 1
                            if result:
                                self.applied_count += 1
                                self.consecutive_fail_streak = 0
                                event_data: dict = {"job_id": str(jobID), "title": job_title, "company": company}
                                if sponsor_score is not None:
                                    event_data["sponsor_score"] = sponsor_score
                                    event_data["sponsor_matched_name"] = sponsor_matched_name
                                self._emit("job_applied", event_data)
                            else:
                                self.failed_count += 1
                                self._emit("job_failed", {"job_id": str(jobID), "title": job_title, "error": "submit failed"})
                                self.consecutive_fail_streak += 1
                                if self.consecutive_fail_streak >= self.MAX_CONSECUTIVE_FAILURES:
                                    raise ConsecutiveFailuresException(f"{self.MAX_CONSECUTIVE_FAILURES} consecutive application failures")
                        except TimeoutError:
                            self.failed_count += 1
                            self._emit("job_failed", {"job_id": str(jobID), "title": job_title, "company": company, "error": "timeout"})
                            self._dismiss_modal()
                            self.consecutive_fail_streak += 1
                            if self.consecutive_fail_streak >= self.MAX_CONSECUTIVE_FAILURES:
                                raise ConsecutiveFailuresException(f"{self.MAX_CONSECUTIVE_FAILURES} consecutive application failures")
                            continue
                        except DailyLimitReachedException:
                            raise
                        except ConsecutiveFailuresException:
                            raise
                        except Exception as e:
                            log.warning(f"Exception applying to job {jobID}: {e}")
                            self.failed_count += 1
                            self._emit("job_failed", {"job_id": str(jobID), "title": job_title, "company": company, "error": str(e)})
                            self.consecutive_fail_streak += 1
                            if self.consecutive_fail_streak >= self.MAX_CONSECUTIVE_FAILURES:
                                raise ConsecutiveFailuresException(f"{self.MAX_CONSECUTIVE_FAILURES} consecutive application failures")
                            continue
                    else:
                        log.info("The button does not exist.")
                        result = False

                    self._emit("progress", {
                        "applied": self.applied_count,
                        "failed": self.failed_count,
                        "total_seen": self.total_seen,
                    })

                    if count_application != 0 and count_application % 20 == 0:
                        sleepTime = random.randint(100, 300)
                        log.info(f"Time for a nap - see you in: {int(sleepTime / 60)} min")
                        time.sleep(sleepTime)

                # Advance to next page after processing all jobs on this page.
                # Unconditional so H1B-filtered or blacklisted jobs don't strand
                # the browser on a detail page and trigger premature exit.
                if jobIDs:
                    jobs_per_page += 25
                    log.info("Going to next jobs page")
                    self.avoid_lock()
                    self.browser, jobs_per_page = self.next_jobs_page(position, location, jobs_per_page)

            except DailyLimitReachedException:
                raise
            except ConsecutiveFailuresException:
                raise
            except Exception as e:
                log.error(f"Exception in main application loop: {e}")
                self._emit("error", {"message": str(e)})

    # ------------------------------------------------------------------
    # Page / job helpers
    # ------------------------------------------------------------------

    def get_job_page(self, jobID):
        job = 'https://www.linkedin.com/jobs/view/' + str(jobID)
        try:
            self.browser.get(job)
        except TimeoutException:
            log.warning(f"Page load timed out for job {jobID}, skipping")
            return None
        self.job_page = self.load_page()
        return self.job_page

    def get_easy_apply_button(self):
        if self._check_daily_limit():
            log.info("Daily application limit detected before button check")
            raise DailyLimitReachedException("Daily application limit reached")
        try:
            button = self.browser.find_elements("xpath", '//*[contains(@aria-label, "Easy Apply to") or contains(@aria-label, "LinkedIn Apply to")]')
            if len(button) == 0:
                return False
            self.browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", button[0])
            time.sleep(0.3)
            try:
                button[0].click()
            except Exception:
                self.browser.execute_script("arguments[0].click();", button[0])
            time.sleep(1)

            if self._check_daily_limit():
                log.info("Daily application limit detected after button click")
                raise DailyLimitReachedException("Daily application limit reached")

            return True
        except DailyLimitReachedException:
            raise
        except Exception as e:
            log.error(f"exception in get_easy_apply_button: {e}")
            return False

    def wait_for_loader_to_disappear(self, timeout=10):
        try:
            WebDriverWait(self.browser, timeout).until(
                EC.invisibility_of_element_located((By.CLASS_NAME, "jobs-loader"))
            )
        except Exception:
            pass
        time.sleep(0.5)

    def fill_out_phone_number(self):
        def is_present(button_locator) -> bool:
            return len(self.browser.find_elements(button_locator[0], button_locator[1])) > 0

        try:
            next_locater = (By.CSS_SELECTOR, "button[aria-label='Continue to next step']")
            input_field = self.browser.find_element("xpath", "//input[contains(@id,'phoneNumber')]")
            if input_field:
                input_field.clear()
                input_field.send_keys(self.phone_number)
                time.sleep(random.uniform(4.5, 6.5))

                next_locater = (By.CSS_SELECTOR, "button[aria-label='Continue to next step']")
                error_locator = (By.CLASS_NAME, "artdeco-inline-feedback__message")

                button = None
                if is_present(next_locater):
                    button = self.wait.until(EC.element_to_be_clickable(next_locater))

                if is_present(error_locator):
                    for element in self.browser.find_elements(error_locator[0], error_locator[1]):
                        text = element.text
                        if "Please enter" in text:
                            button = None
                            break
                if button:
                    button.click()
                    time.sleep(random.uniform(1.5, 2.5))
        except Exception:
            log.debug("Could not find phone number field")

    def _dismiss_modal(self) -> None:
        """Attempt to dismiss any open Easy Apply modal after a timeout or error."""
        for selector in [
            "button[aria-label='Dismiss']",
            "button[aria-label='Cancel']",
        ]:
            try:
                btn = self.browser.find_element(By.CSS_SELECTOR, selector)
                btn.click()
                time.sleep(0.5)
                return
            except Exception:
                pass
        # Fallback: send Escape key to close any open overlay
        try:
            self.browser.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass

    def send_resume(self, deadline: Optional[float] = None) -> bool:
        def has_errors() -> bool:
            return len(self.browser.find_elements(By.XPATH, '//*[contains(@type, "error-pebble-icon")]')) > 0

        try:
            # Wait for the Easy Apply modal to appear before looking for buttons
            try:
                WebDriverWait(self.browser, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "div.jobs-easy-apply-content, div.jobs-easy-apply-modal"))
                )
            except TimeoutException:
                log.warning("Easy Apply modal did not appear within 10s")
                return False
            time.sleep(random.uniform(0.3, 0.8))

            next_locater = (By.XPATH, "//button[contains(@aria-label,'Continue to next step') or contains(@aria-label,'continue to next step')]")
            review_locater = (By.XPATH, "//button[contains(@aria-label,'Review your application') or contains(@aria-label,'review your application')]")
            submit_locater = (By.XPATH, "//button[contains(@aria-label,'Submit application') or contains(@aria-label,'submit application')]")
            submit_btn_locator = (By.CSS_SELECTOR, "button[data-live-test-easy-apply-submit-button]")
            error_locator = (By.CLASS_NAME, "artdeco-inline-feedback__message")
            follow_locator = (By.CSS_SELECTOR, "label[for='follow-company-checkbox']")

            buttons = [next_locater, review_locater,
                       submit_locater, submit_btn_locator]

            def _find_any_button(driver):
                """Return (index, element) for the first action button found, or False."""
                for idx, loc in enumerate(buttons):
                    elems = driver.find_elements(loc[0], loc[1])
                    if elems:
                        return (idx, elems[0])
                return False

            submitted = False
            no_progress_count = 0
            while True:
                if deadline is not None and time.time() > deadline:
                    raise TimeoutError("Job application timed out")
                if self.stopped:
                    return False

                # Uncheck "follow company" if present (before looking for action buttons)
                try:
                    follow_els = self.browser.find_elements(follow_locator[0], follow_locator[1])
                    if follow_els:
                        follow_els[0].click()
                        time.sleep(0.3)
                except Exception:
                    pass

                # Poll for any action button for up to 5 seconds (0.5s intervals)
                button = None
                button_idx = None
                try:
                    result = WebDriverWait(self.browser, 5).until(_find_any_button)
                    button_idx, button = result
                except TimeoutException:
                    pass

                # Handle form validation errors regardless of button state
                if self.browser.find_elements(error_locator[0], error_locator[1]):
                    try:
                        for element in self.browser.find_elements(error_locator[0], error_locator[1]):
                            text = element.text
                            if "integer" in text.lower() or "whole number" in text.lower():
                                try:
                                    inp = element.find_element(By.XPATH, "./ancestor::div[contains(@class,'fb-dash-form-element')][1]//input")
                                    inp.clear()
                                    inp.send_keys(str(self.years_of_experience))
                                    log.info(f"Replaced non-integer value with years_of_experience due to: {text}")
                                except Exception as ie:
                                    log.debug(f"Could not fix integer field: {ie}")
                            elif ("Please enter" in text or "Please make" in text or "Enter a" in text or "Select checkbox to proceed") and not self.checked_invalid:
                                self.fill_invalids()
                                break
                    except Exception as e:
                        log.info(e)


                if button:
                    no_progress_count = 0
                    self.browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(0.3)
                    try:
                        button.click()
                    except Exception:
                        self.browser.execute_script("arguments[0].click();", button)
                    time.sleep(random.uniform(0.5, 1.5))
                    if button_idx in (2, 3):
                        submitted = True
                    if submitted:
                        break
                    continue
                else:
                    no_progress_count += 1
                    if no_progress_count == 2:
                        try:
                            modal_buttons = self.browser.find_elements(By.CSS_SELECTOR, "div.jobs-easy-apply-content button")
                            labels = [b.get_attribute("aria-label") or b.text.strip() for b in modal_buttons[:10]]
                            log.debug(f"Modal buttons found: {labels}")
                        except Exception:
                            pass
                    if no_progress_count >= 6:
                        log.warning("No actionable buttons found after 30s, abandoning application")
                        return False

                if submitted:
                    self.checked_invalid = False
                    log.info("Application Submitted")
                    break

            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            log.info(f"{e} - cannot apply to this job")
            raise e

        return submitted

    # ------------------------------------------------------------------
    # Field label / value helpers
    # ------------------------------------------------------------------

    def get_field_label(self, input_element):
        try:
            input_id = input_element.get_attribute('id')
            if input_id:
                label = self.browser.find_element(By.XPATH, f"//label[@for='{input_id}']")
                if label:
                    return label.text.strip()
            parent_label = input_element.find_element(By.XPATH, "./ancestor::label")
            if parent_label:
                return parent_label.text.strip()
            label_elements = self.browser.find_elements(By.XPATH, "//label")
            for label in label_elements:
                if label.is_displayed():
                    label_rect = label.rect
                    input_rect = input_element.rect
                    if (abs(label_rect['y'] - input_rect['y']) < 50 and
                            abs(label_rect['x'] - input_rect['x']) < 200):
                        return label.text.strip()
            placeholder = input_element.get_attribute('placeholder')
            if placeholder:
                return placeholder.strip()
            aria_label = input_element.get_attribute('aria-label')
            if aria_label:
                return aria_label.strip()
        except Exception as e:
            log.debug(f"Could not extract label for input: {e}")
        return ""

    def get_appropriate_value(self, label_text, input_type="text"):
        label_lower = label_text.lower()

        if any(keyword in label_lower for keyword in ['phone', 'mobile', 'telephone', 'contact']):
            return self.phone_number
        if 'city' in label_lower or 'location' in label_lower or 'reside' in label_lower:
            return self.location
        if 'have you ever worked' in label_lower:
            return 'No'
        if 'state' in label_lower:
            return self.user_state
        if 'zip' in label_lower or 'postal' in label_lower:
            return self.zip_code
        if any(keyword in label_lower for keyword in ['salary', 'wage', 'income']):
            return self.desired_salary
        if 'experience' in label_lower and 'years' in label_lower:
            return self.years_of_experience
        if ('available' in label_lower or 'start' in label_lower or 'notice' in label_lower) and 'hour' not in label_lower:
            return '2 weeks'
        if any(keyword in label_lower for keyword in ['skill', 'technology', 'programming', 'language']):
            return 'Python, JavaScript, SQL'
        if any(keyword in label_lower for keyword in ['education', 'degree', 'university', 'college']):
            return 'Bachelor'
        if any(keyword in label_lower for keyword in ['linkedin', 'linked-in', 'linked in']):
            return self.linkedin_profile_url
        if any(keyword in label_lower for keyword in ['github', 'git hub']):
            return self.github_url
        if any(keyword in label_lower for keyword in ['portfolio', 'personal site', 'personal website', 'website']):
            return self.portfolio_url

        if input_type == "text":
            llm_answer = self.get_llm_suggested_answer(label_text, input_type)
            return llm_answer

        return ''

    def fill_invalids(self):
        try:
            location = self.browser.find_element(By.CSS_SELECTOR, "input[id*='GEO-LOCATION']")
        except Exception:
            location = None

        if location:
            location.send_keys(self.location)
            time.sleep(1)
            try:
                dropdown_option = WebDriverWait(self.browser, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//div[contains(@class, 'basic-typeahead__selectable')]//span[contains(@class, 'search-typeahead-v2__hit-text')]"
                    ))
                )
                dropdown_option.click()
                time.sleep(1)
            except Exception:
                pass
            return

        try:
            your_name_label = self.browser.find_element(By.XPATH, "//label[contains(text(), 'Your Name')]")
            
        except Exception as e:
            your_name_label = None
            
        if your_name_label:
            input_id = your_name_label.get_attribute('for') if your_name_label else None
            input_element = self.browser.find_element(By.ID, input_id)
            input_element.clear()
            name = self.config.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
            input_element.send_keys(name)

        text_inputs = self.browser.find_elements(By.XPATH,
            '//input[contains(@class, "fb-dash-form-element") '
            'or contains(@class, "artdeco-text-input--input")]')
        for input_element in text_inputs:
            try:
                # Date picker inputs (name="artdeco-date", placeholder mm/dd/yyyy)
                if input_element.get_attribute('name') == 'artdeco-date' or \
                        (input_element.get_attribute('placeholder') or '').startswith('mm/dd'):
                    start_date = (datetime.date.today() + datetime.timedelta(weeks=2)).strftime('%-m/%-d/%Y')
                    input_element.clear()
                    input_element.send_keys(start_date)
                    log.info(f"Filled date picker with: {start_date}")
                    continue

                label_text = self.get_field_label(input_element)
                input_type = input_element.get_attribute('type') or 'text'
                appropriate_value = self.get_appropriate_value(label_text, input_type)
                if appropriate_value:
                    input_element.clear()
                    input_element.send_keys(appropriate_value)
                    log.info(f"Filled field '{label_text}' with value: {appropriate_value}")
                else:
                    input_element.clear()
                    input_element.send_keys('3')
                    log.info(f"Filled field '{label_text}' with default value: 3")
            except Exception as e:
                log.error(f"Error filling input field: {e}")
                try:
                    input_element.clear()
                    input_element.send_keys('3')
                except Exception:
                    pass

        time.sleep(1)

        # Unified radio fieldset handler — works with any option label format
        radio_fieldsets = self.browser.find_elements(
            By.XPATH, '//fieldset[@data-test-form-builder-radio-button-form-component]')
        for fieldset in radio_fieldsets:
            try:
                legend = fieldset.find_element(By.TAG_NAME, 'legend')
                question_text = legend.text.strip()
                question_lower = question_text.lower()
                inputs = fieldset.find_elements(By.XPATH, './/input[@data-test-text-selectable-option__input]')
                if not inputs:
                    continue

                # Pick "no"-starting option for questions that ask if you *need* sponsorship/visa.
                # Questions asking if you're *eligible/authorized* (i.e. "without sponsorship") want "yes".
                needs_no = (
                    any(kw in question_lower for kw in ['visa', 'sponsor', 'work authorization'])
                    and not any(kw in question_lower for kw in ['eligible', 'without', 'authorized to work', 'able to work'])
                )

                # For any fieldset, prefer "I don't wish to answer" / "I prefer not to answer" if present
                _decline_option = next(
                    (i for i in inputs if any(kw in (i.get_attribute('data-test-text-selectable-option__input') or '').lower()
                                              for kw in ["don't wish", "do not wish", "prefer not", "decline to"])),
                    None)

                if _decline_option:
                    target = _decline_option
                elif any(kw in question_lower for kw in ['citizenship', 'employment eligibility']):
                    # Select "U.S Citizen / Permanent Resident" if present, otherwise first option
                    target = next(
                        (i for i in inputs if 'u.s citizen' in (i.get_attribute('data-test-text-selectable-option__input') or '').lower()),
                        inputs[0])
                elif any(kw in question_lower for kw in ['acknowledge', 'confidential', 'consent', 'declare', 'privacy notice']):
                    # Consent/acknowledgment statement — pick the affirmative option (no "not" in label)
                    def _is_affirmative(inp):
                        lbl = (inp.get_attribute('data-test-text-selectable-option__input') or '').lower()
                        return any(kw in lbl for kw in ['acknowledge', 'agree', 'consent', 'understand']) \
                               and 'not' not in lbl and 'do not' not in lbl
                    target = next((i for i in inputs if _is_affirmative(i)), inputs[0])
                elif needs_no:
                    target = next(
                        (i for i in inputs if (i.get_attribute('data-test-text-selectable-option__input') or '').lower().startswith('no')),
                        None)
                else:
                    target = next(
                        (i for i in inputs if (i.get_attribute('data-test-text-selectable-option__input') or '').lower().startswith('yes')),
                        None)

                if not target:
                    # LLM fallback for unrecognized radio question
                    option_texts = [
                        i.get_attribute('data-test-text-selectable-option__input') or ''
                        for i in inputs
                    ]
                    option_texts = [t for t in option_texts if t]
                    if option_texts:
                        llm_answer = self.get_llm_suggested_answer(question_text, options=option_texts)
                        if llm_answer:
                            def _norm(s):
                                return re.sub(r'[–—−]', '-', s).lower()
                            # Try substring match, then dash-normalized match
                            target = next(
                                (i for i in inputs if llm_answer.lower() in
                                 (i.get_attribute('data-test-text-selectable-option__input') or '').lower()),
                                None,
                            )
                            if not target:
                                target = next(
                                    (i for i in inputs if _norm(llm_answer) in _norm(
                                        i.get_attribute('data-test-text-selectable-option__input') or '')),
                                    None,
                                )
                    if not target:
                        # Last resort: pick first option to unblock form rather than leaving blank
                        target = inputs[0]
                        log.warning(f"No match for radio question '{question_text}' — selecting first option")

                element_to_click = self.browser.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});"
                    "var r = arguments[0].getBoundingClientRect();"
                    "return document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);",
                    target)
                element_to_click.click()
                log.info(f"Selected '{target.get_attribute('data-test-text-selectable-option__input')}' for: {question_text}")
            except Exception as e:
                log.error(f"Error handling radio fieldset: {e}")
        time.sleep(1)

        # Checkbox fieldsets — consent notices and referral source questions
        checkbox_fieldsets = self.browser.find_elements(
            By.XPATH, '//fieldset[@data-test-checkbox-form-component]')
        for fieldset in checkbox_fieldsets:
            try:
                legend_text = ''
                try:
                    legend_text = fieldset.find_element(By.TAG_NAME, 'legend').text.lower()
                except Exception:
                    pass

                inputs = fieldset.find_elements(
                    By.XPATH, './/input[@type="checkbox"][@data-test-text-selectable-option__input]')
                if not inputs:
                    continue

                def _click_checkbox(inp):
                    if not inp.is_selected():
                        self.browser.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});"
                            "var r = arguments[0].getBoundingClientRect();"
                            "document.elementFromPoint(r.left + r.width/2, r.top + r.height/2).click();",
                            inp)

                # Consent / privacy / declaration → check matching option or first available
                if any(kw in legend_text for kw in ['consent', 'agree', 'acknowledge', 'declare', 'privacy', 'understand']):
                    target = next(
                        (inp for inp in inputs
                         if any(kw in (inp.get_attribute('data-test-text-selectable-option__input') or '').lower()
                                for kw in ['consent', 'agree', 'acknowledge', 'understand'])),
                        inputs[0])
                    _click_checkbox(target)
                    log.info(f"Checked consent checkbox: {target.get_attribute('data-test-text-selectable-option__input')}")

                # "How did you hear about us?" → prefer LinkedIn, fall back to first option
                elif any(kw in legend_text for kw in ['hear about', 'how did you find', 'referral', 'source']):
                    labels = [(inp.get_attribute('data-test-text-selectable-option__input') or '').lower()
                              for inp in inputs]
                    target = next(
                        (inputs[i] for i, l in enumerate(labels) if 'linkedin' in l),
                        inputs[0])
                    _click_checkbox(target)
                    log.info(f"Selected referral source: {target.get_attribute('data-test-text-selectable-option__input')}")

                # Security clearance → select "Never held a clearance" or last option (lowest level)
                elif any(kw in legend_text for kw in ['clearance', 'security clearance', 'secret', 'classified']):
                    labels = [(inp.get_attribute('data-test-text-selectable-option__input') or '').lower()
                              for inp in inputs]
                    target = next(
                        (inputs[i] for i, l in enumerate(labels) if 'never' in l),
                        inputs[-1])
                    _click_checkbox(target)
                    log.info(f"Selected clearance option: {target.get_attribute('data-test-text-selectable-option__input')}")

                # Unrecognized required checkbox fieldset → check first option to unblock
                else:
                    if not any(inp.is_selected() for inp in inputs):
                        _click_checkbox(inputs[0])
                        log.info(f"Checked first option on unrecognized checkbox fieldset: {legend_text!r}")

            except Exception as e:
                log.error(f"Error handling checkbox fieldset: {e}")
        time.sleep(1)

        try:
            select_inputs = self.browser.find_elements(By.CSS_SELECTOR, 'select[aria-required="true"]')
            for inp in select_inputs:
                question_text = self.get_select_question_text(inp)
                question_lower = question_text.lower()
                select_obj = Select(inp)
                if "country" in question_lower:
                    try:
                        us_opt = next(
                            (o for o in select_obj.options
                             if o.get_attribute('value').lower() == 'united states'),
                            None
                        )
                        if us_opt:
                            select_obj.select_by_visible_text(us_opt.text)
                            log.info(f"Selected '{us_opt.text}' for country question: {question_text}")
                        else:
                            log.warning(f"'United States' not found in options for: {question_text}")
                    except Exception as e:
                        log.error(f"Could not select country for '{question_text}': {e}")
                    continue
                options = select_obj.options
                non_placeholder = [o for o in options if (o.get_attribute('value') or '').lower() not in ('select an option', '', 'select')]
                selected = False

                # Experience/years range: pick the bucket that fits years_of_experience
                if any(kw in question_lower for kw in ['years of experience', 'years experience', 'years of industry', 'how many years']):
                    yoe_str = str(self.years_of_experience).strip()
                    yoe = int(yoe_str) if yoe_str.isdigit() else 0
                    for opt in non_placeholder:
                        ot = opt.text
                        range_match = re.search(r'(\d+)\s*[-–]\s*(\d+)', ot)
                        plus_match = re.search(r'(\d+)\+', ot)
                        if range_match:
                            lo, hi = int(range_match.group(1)), int(range_match.group(2))
                            if lo <= yoe <= hi:
                                select_obj.select_by_visible_text(opt.text)
                                log.info(f"Selected experience range '{opt.text}' for: {question_text}")
                                selected = True
                                break
                        elif plus_match:
                            lo = int(plus_match.group(1))
                            if yoe >= lo:
                                select_obj.select_by_visible_text(opt.text)
                                log.info(f"Selected experience range '{opt.text}' for: {question_text}")
                                selected = True
                                break
                    if not selected and non_placeholder:
                        # No bucket matched — pick the last option (highest range)
                        select_obj.select_by_visible_text(non_placeholder[-1].text)
                        log.info(f"Selected last experience option '{non_placeholder[-1].text}' for: {question_text}")
                        selected = True

                if not selected:
                    for option in options:
                        ot = option.text.lower()
                        if "united states" in ot:
                            select_obj.select_by_visible_text(option.text)
                            log.info(f"Selected option '{option.text}' for question: {question_text}")
                            selected = True
                        elif "immediate family" in question_lower and "no" in ot:
                            select_obj.select_by_visible_text(option.text)
                            log.info(f"Selected option '{option.text}' for question: {question_text}")
                            selected = True
                        elif "no" in ot and "require" in question_lower:
                            select_obj.select_by_visible_text(option.text)
                            log.info(f"Selected option '{option.text}' for question: {question_text}")
                            selected = True
                        elif any(word in ot for word in ["confirm", "accept", "acknowledge", "consent", "human being"]):
                            select_obj.select_by_visible_text(option.text)
                            log.info(f"Selected option '{option.text}' for question: {question_text}")
                            selected = True
                        elif ("yes" in ot and "do you require" not in question_lower) or "native" in ot or "U.S." in ot or "us" in ot or "linkedin" in ot or "united states" in ot or "citizen" in ot:
                            select_obj.select_by_visible_text(option.text)
                            log.info(f"Selected option '{option.text}' for question: {question_text}")
                            selected = True

                # Fallback: nothing matched — pick first non-placeholder option to unblock
                if not selected and non_placeholder:
                    select_obj.select_by_visible_text(non_placeholder[0].text)
                    log.info(f"Selected first available option '{non_placeholder[0].text}' for unrecognized question: {question_text}")
        except Exception as e:
            select_inputs = None

        text_area_inputs = self.browser.find_elements(By.XPATH, '//textarea[contains(@class, "fb-dash-form-element")]')
        for textarea in text_area_inputs:
            try:
                label_text = self.get_field_label(textarea)
                appropriate_value = self.get_appropriate_value(label_text, input_type="text")
                if appropriate_value:
                    textarea.clear()
                    textarea.send_keys(appropriate_value)
                    log.info(f"Filled textarea '{label_text}' with value: {appropriate_value}")
                else:
                    log.warning(f"No answer generated for textarea '{label_text}', leaving blank")
            except Exception as e:
                log.error(f"Error filling textarea field: {e}")

    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 2000:
            self.browser.execute_script("window.scrollTo(0," + str(scroll_page) + " );")
            scroll_page += 200
            time.sleep(sleep)
        page = BeautifulSoup(self.browser.page_source, "lxml")
        return page

    def avoid_lock(self) -> None:
        if pyautogui is None:
            return
        try:
            pyautogui.FAILSAFE = False
            time.sleep(0.5)
            pyautogui.press('esc')
        except Exception as e:
            log.debug(f"avoid_lock skipped (no display?): {e}")

    def next_jobs_page(self, position, location, jobs_per_page):
        self.browser.get(
            "https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords=" +
            position + location + "&sortBy=DD&start=" + str(jobs_per_page))
        self.avoid_lock()
        self.load_page()
        if self._check_daily_limit():
            log.info("Daily application limit detected before search")
            raise DailyLimitReachedException("Daily application limit reached")
        return (self.browser, jobs_per_page)

    def finish_apply(self) -> None:
        self.browser.close()

    def get_radio_question_text(self, input_element):
        try:
            fieldset = input_element.find_element(By.XPATH, "./ancestor::fieldset[1]")
            return fieldset.accessible_name
        except Exception as e:
            log.debug(f"Could not extract radio question text: {e}")
        return ""

    def get_select_question_text(self, select_element):
        try:
            select_id = select_element.get_attribute('id')
            if select_id:
                label = self.browser.find_element(By.XPATH, f"//label[@for='{select_id}']")
                if label:
                    return label.text.strip()
            parent_label = select_element.find_element(By.XPATH, "./ancestor::label[1]")
            if parent_label:
                return parent_label.text.strip()
            label = select_element.find_element(By.XPATH, "preceding-sibling::label[1]")
            if label:
                return label.text.strip()
            aria_label = select_element.get_attribute('aria-label')
            if aria_label:
                return aria_label.strip()
        except Exception as e:
            log.debug(f"Could not extract select question text: {e}")
        return ""

    def _build_llm_prompt(self, label_text):
        name = self.config.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
        positions_str = ', '.join(self.config.positions) if self.config.positions else "Software Engineer"
        location_str = self.location or "United States"
        yoe = self.years_of_experience or "3"
        salary = self.desired_salary or "100000"
        extra = ""
        if self.github_url:
            extra += f"\nGitHub: {self.github_url}"
        if self.portfolio_url:
            extra += f"\nPortfolio/website: {self.portfolio_url}"
        numeric_fields = (
            "Questions asking ONLY for a number (e.g. 'How many years of experience', 'Years of experience', "
            "'Expected salary / hourly rate', 'How many hours per week') should be answered with ONLY a single "
            f"numeric value and no other text: use {yoe} for years/experience questions, {salary} for salary/wage questions. "
            f"If the question is simply asking for the name of a technology (e.g. 'Python', 'Java', 'AWS'), "
            f"respond with ONLY the number of years of experience: {yoe}. "
            f"If the question is not phrased as a question, assume it is asking for experience with X and respond with {yoe}"
            "All other questions — including motivation, culture fit, or open-ended questions — require a full prose answer."
        )
        return (
            f"You are {name}, a professional applying for jobs as a {positions_str} "
            f"based in {location_str} with {yoe} years of experience.{extra} "
            f"Answer the following job application question in 2-3 concise, professional sentences. "
            f"{numeric_fields} "
            f"Question: '{label_text}'"
        )

    def _llm_openai(self, prompt: str) -> str:
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            return ""
        client = OpenAI(api_key=openai_api_key)
        response = client.responses.create(
            model="gpt-4o",
            input=prompt,
        )
        return response.output_text.strip()

    def _llm_anthropic(self, prompt: str) -> str:
        if _anthropic is None:
            log.warning("anthropic package not installed – skipping LLM fallback")
            return ""
        client = _anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def _llm_gemini(self, prompt: str) -> str:
        if _genai is None:
            log.warning("google-genai package not installed – skipping LLM fallback")
            return ""
        client = _genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text.strip()

    def _llm_ollama(self, prompt: str) -> str:
        if _ollama is None:
            log.warning("ollama package not installed – skipping LLM fallback")
            return ""
        response = _ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"].strip()

    def get_llm_suggested_answer(self, label_text: str, input_type: str = "text", options: Optional[List[str]] = None) -> str:
        provider = os.environ.get("HIRINGFUNNEL_AI_PROVIDER", "openai").lower()
        if options:
            prompt = (
                f"Job application form question: {label_text}\n"
                f"Options: {', '.join(options)}\n"
                f"Reply with ONLY the exact option text that best applies. No explanation."
            )
        else:
            prompt = self._build_llm_prompt(label_text)
        try:
            if provider == "openai":
                answer = self._llm_openai(prompt)
            elif provider == "anthropic":
                answer = self._llm_anthropic(prompt)
            elif provider == "gemini":
                answer = self._llm_gemini(prompt)
            elif provider == "ollama":
                answer = self._llm_ollama(prompt)
            else:
                log.warning(f"Unknown AI provider '{provider}' – skipping LLM fallback")
                return ""
            if answer:
                log.info(f"LLM suggested answer for '{label_text}': {answer}")
            return answer
        except Exception as e:
            log.error(f"LLM request failed ({provider}): {e}")
        return ""


# ---------------------------------------------------------------------------
# Bot runner
# ---------------------------------------------------------------------------

_bot: Optional[EasyApplyBot] = None
_bot_thread: Optional[threading.Thread] = None
_bot_lock = threading.Lock()
_applying = False
_profile_browser: Optional[webdriver.Chrome] = None


def open_linkedin_profile(config: ProfileConfig, on_event: Optional[Callable] = None) -> bool:
    """Launch browser, log in to LinkedIn, navigate to profile_url. Returns True on success."""
    global _profile_browser

    def _emit(event_type, data=None):
        if on_event:
            try:
                on_event(event_type, data or {})
            except Exception:
                pass

    if _profile_browser is not None:
        try:
            _profile_browser.quit()
        except Exception:
            pass
        _profile_browser = None

    driver = _make_chrome_driver()

    try:
        driver.get("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
        user_field = driver.find_element("id", "username")
        pw_field = driver.find_element("id", "password")
        login_button = driver.find_element(By.CLASS_NAME, "btn__primary--large")
        user_field.send_keys(config.email)
        user_field.send_keys(Keys.TAB)
        time.sleep(2)
        pw_field.send_keys(config.password)
        time.sleep(2)
        login_button.click()
        time.sleep(3)
    except Exception as e:
        _emit("login_failed", {"error": str(e)})
        driver.quit()
        return False

    if config.profile_url:
        try:
            driver.get(config.profile_url)
        except Exception:
            pass

    _profile_browser = driver
    _emit("browser_ready")
    return True


def _run_bot(config: ProfileConfig, on_event: Optional[Callable[[str, dict], None]] = None):
    """Target function for the bot background thread."""
    global _bot, _applying
    # Inject AI provider + key into os.environ before constructing the bot
    settings = load_settings()
    _inject_ai_env(settings)
    try:
        _bot = EasyApplyBot(config, on_event=on_event,
                            blacklist=settings.blacklist,
                            blacklist_titles=settings.blacklist_titles)

        if not _bot.start_linkedin(config.email, config.password):
            if on_event:
                on_event("bot_stopped", {"reason": "login_failed"})
            _bot.close()
            _bot = None
            _applying = False
            return

        # H-1B seeded check: verify the employer table is populated before
        # starting a visa-mode run. Raises H1BAPIUnavailableException if not.
        if config.requires_visa:
            _bot._check_h1b_seeded()

        if on_event:
            on_event("bot_started", {"requires_visa": config.requires_visa})
        _applying = True

        positions = [p for p in config.positions if p]
        locations = [loc for loc in config.locations if loc]

        if not positions or not locations:
            if on_event:
                on_event("bot_stopped", {"reason": "no positions or locations configured"})
            _bot.close()
            _bot = None
            _applying = False
            return

        _bot.start_apply(positions, locations)
        if on_event and config.requires_visa:
            on_event("h1b_session_summary", {"lines": _bot._h1b_summary_lines(), "stats": dict(_bot._h1b_stats)})
        if on_event:
            on_event("bot_stopped", {"reason": "completed"})
    except DailyLimitReachedException:
        log.info(f"Daily application limit reached for {config.email}")
        if on_event:
            on_event("daily_limit_reached", {"profile_email": config.email})
            on_event("bot_stopped", {"reason": "daily_limit_reached"})
    except H1BAPIUnavailableException as e:
        log.error(f"H-1B API unavailable for {config.email}: {e}")
        if on_event:
            on_event("h1b_api_unavailable", {"message": str(e)})
            on_event("bot_stopped", {"reason": "h1b_api_unavailable"})
    except ConsecutiveFailuresException:
        log.warning(f"{EasyApplyBot.MAX_CONSECUTIVE_FAILURES} consecutive failures for {config.email}, moving to next profile")
        if on_event:
            on_event("consecutive_failures_exceeded", {
                "profile_email": config.email,
                "applied": _bot.applied_count if _bot else 0,
                "failed": _bot.failed_count if _bot else 0,
            })
            on_event("bot_stopped", {"reason": "consecutive_failures_exceeded"})
    except Exception as e:
        log.error(f"Bot thread exception: {e}")
        if on_event:
            on_event("error", {"message": str(e)})
            on_event("bot_stopped", {"reason": f"error: {e}"})
    finally:
        if _bot:
            _bot.close()
            _bot = None
        _applying = False
