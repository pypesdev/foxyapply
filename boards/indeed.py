"""Indeed adapter.

Authentication strategy: cookie-based session persistence
=========================================================
Because Indeed accounts linked to Google/Apple OAuth cannot be automated
through Selenium (Google blocks bot sign-ins), we use saved browser cookies:

  First run:
    1. Bot opens Chrome and navigates to the Indeed login page.
    2. A message is printed in the TUI: "Please log in manually."
    3. You log in however you normally would (Google, Apple, email+code…).
    4. Once detected as logged in, cookies are saved to
       ~/.hiringfunnel/indeed_session.pkl
    5. The apply loop continues automatically.

  Subsequent runs:
    Cookies are loaded from disk — no manual login needed.
    Cookies typically stay valid for several weeks.

  If a session expires:
    Delete ~/.hiringfunnel/indeed_session.pkl  and the manual-login
    prompt will appear again on the next run.
"""

from __future__ import annotations

import os
import pickle
import time
from typing import TYPE_CHECKING, Callable, List, Optional
from urllib.parse import quote_plus

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .base import JobBoardBot

if TYPE_CHECKING:
    from easyapplybot import ProfileConfig


class IndeedBot(JobBoardBot):
    name = "indeed"
    display_name = "Indeed"

    # ------------------------------------------------------------------
    # URLs  (update if Indeed changes routing)
    # ------------------------------------------------------------------

    # Landing page for the email+password sign-in flow
    LOGIN_URL = (
        "https://secure.indeed.com/auth"
        "?hl=en_US&co=US&continue=%2F&service=my&from=gnav-util-homepage"
    )

    # Search results.  Params:
    #   q        = URL-encoded job title / keywords
    #   l        = URL-encoded location ("Remote", "New York, NY", etc.)
    #   filter   = 0  (show all, not just "unique" results)
    #   start    = result offset for pagination (0, 15, 30, …)
    #   fromage  = max days since posting (remove to search all time)
    SEARCH_URL_TEMPLATE = (
        "https://www.indeed.com/jobs"
        "?q={query}&l={location}&filter=0&start={start}&fromage=14"
    )

    RESULTS_PER_PAGE = 15  # Indeed returns 15 cards per page

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(
        self,
        config: "ProfileConfig",
        on_event: Optional[Callable] = None,
    ) -> None:
        super().__init__(config, on_event)
        from easyapplybot import _make_chrome_driver
        self.driver = _make_chrome_driver()
        self.wait = WebDriverWait(self.driver, 30)

    def close(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Entry point called by the orchestrator
    # ------------------------------------------------------------------

    def run(self, positions: List[str], locations: List[str]) -> None:
        if not self.login():
            self._emit("login_failed", {"board": self.name})
            return
        self._emit("login_success", {"board": self.name})

        for position in positions:
            for location in locations:
                if self.should_stop:
                    return
                self._apply_for(position, location)

    # ------------------------------------------------------------------
    # Login — cookie-based session persistence
    # ------------------------------------------------------------------

    COOKIES_FILE = os.path.expanduser("~/.hiringfunnel/indeed_session.pkl")
    MANUAL_LOGIN_TIMEOUT = 180  # seconds to wait for manual login

    def login(self) -> bool:
        """Restore a saved session or prompt for manual login."""
        if self._try_cookie_login():
            return True
        return self._manual_login_wait()

    def _try_cookie_login(self) -> bool:
        """Load saved cookies and check if the session is still valid."""
        if not os.path.exists(self.COOKIES_FILE):
            return False
        try:
            # Must visit the domain before adding cookies
            self.driver.get("https://www.indeed.com")
            time.sleep(1)
            with open(self.COOKIES_FILE, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass
            self.driver.refresh()
            time.sleep(2)
            if self._is_logged_in():
                return True
            # Session expired — delete stale cookies and fall through
            log.info("Saved Indeed session expired, falling back to manual login")
            self._emit("cookie_login_expired", {"board": self.name})
            os.remove(self.COOKIES_FILE)
            return False
        except Exception as e:
            log.warning(f"Cookie login failed: {e}")
            try:
                os.remove(self.COOKIES_FILE)
            except OSError:
                pass
            return False

    def _manual_login_wait(self) -> bool:
        """Open the login page and wait up to MANUAL_LOGIN_TIMEOUT seconds
        for the user to sign in manually (Google, Apple, email — anything)."""
        self.driver.get(self.LOGIN_URL)
        self._emit("login_manual_required", {
            "board": self.name,
            "message": (
                "Please log in to Indeed in the Chrome window that just opened. "
                f"Waiting up to {self.MANUAL_LOGIN_TIMEOUT // 60} minutes..."
            ),
        })

        deadline = time.time() + self.MANUAL_LOGIN_TIMEOUT
        while time.time() < deadline:
            time.sleep(3)
            if self._is_logged_in():
                self._save_cookies()
                return True
        return False

    def _is_logged_in(self) -> bool:
        url = self.driver.current_url
        return (
            "indeed.com" in url
            and "/account/login" not in url
            and "/auth" not in url
        )

    def _save_cookies(self) -> None:
        os.makedirs(os.path.dirname(self.COOKIES_FILE), exist_ok=True)
        pickle.dump(self.driver.get_cookies(), open(self.COOKIES_FILE, "wb"))

    # ------------------------------------------------------------------
    # Step 2 — Search
    # ------------------------------------------------------------------

    def _build_search_url(self, position: str, location: str, start: int = 0) -> str:
        return self.SEARCH_URL_TEMPLATE.format(
            query=quote_plus(position),
            location=quote_plus(location),
            start=start,
        )

    def _get_job_cards(self) -> list:
        """Return all visible job card elements on the current search page."""
        return self.driver.find_elements(By.CSS_SELECTOR, "div.job_seen_beacon")

    def _is_easy_apply(self, card) -> bool:
        """Return True if this card has an Indeed Easy Apply badge.

        The badge class names are dynamically generated so we check text instead.
        """
        return "easily apply" in card.text.lower()

    def _get_job_meta(self, card) -> dict:
        """Extract title, company, and job_id from a card element."""
        title = company = job_id = ""
        try:
            anchor = card.find_element(By.CSS_SELECTOR, "a[data-jk]")
            job_id = anchor.get_attribute("data-jk") or ""
            title_span = anchor.find_element(By.CSS_SELECTOR, "span[id^='jobTitle-']")
            title = title_span.text.strip()
        except Exception:
            pass
        try:
            company = card.find_element(
                By.CSS_SELECTOR, "span[data-testid='company-name']"
            ).text.strip()
        except Exception:
            pass
        return {"title": title, "company": company, "job_id": job_id}

    # ------------------------------------------------------------------
    # Step 3 — Click Apply
    # ------------------------------------------------------------------

    def _click_apply(self, card) -> bool:
        """Click the job card title to load the detail pane, then click Apply now."""
        # Click title to open right-pane job detail
        try:
            card.find_element(By.CSS_SELECTOR, "a[data-jk]").click()
            time.sleep(1)
        except Exception:
            return False

        # Wait for and click the Apply now button
        try:
            apply_btn = self.wait.until(
                EC.element_to_be_clickable((By.ID, "indeedApplyButton"))
            )
            apply_btn.click()
            time.sleep(2)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Step 4 — Fill and submit the application
    # ------------------------------------------------------------------

    def _fill_application(self) -> bool:
        """Handle the smartapply.indeed.com tab that opens after clicking Apply now.

        Indeed Smart Apply opens in a new tab.  For many jobs all fields are
        pre-populated and we go straight to Submit.  For multi-step jobs a
        Continue button appears between steps.

        The loop runs up to 10 steps:
          - If Submit button found  → click it, return True
          - If Continue button found → click it, loop again
          - Neither found           → give up, return False

        The apply tab is always closed before returning, and the driver
        switches back to the search results window.
        """
        handles = self.driver.window_handles
        if len(handles) < 2:
            return False

        main_handle = handles[0]
        apply_handle = handles[-1]
        self.driver.switch_to.window(apply_handle)

        try:
            for _ in range(10):
                time.sleep(2)

                # Final step — submit the application
                submit_btns = self.driver.find_elements(
                    By.CSS_SELECTOR, "button[data-testid='submit-application-button']"
                )
                if submit_btns:
                    submit_btns[0].click()
                    time.sleep(2)
                    return True

                # Intermediate step — click Continue
                continue_btns = self.driver.find_elements(
                    By.CSS_SELECTOR, "button[data-testid='continue-button']"
                )
                if continue_btns:
                    continue_btns[0].click()
                    continue

                # No recognised button — bail out
                break

            return False

        finally:
            try:
                self.driver.close()
            except Exception:
                pass
            try:
                self.driver.switch_to.window(main_handle)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Inner apply loop  (orchestrates steps 2–4 per position/location)
    # ------------------------------------------------------------------

    def _apply_for(self, position: str, location: str) -> None:
        """Paginate through search results and apply to Easy Apply jobs."""
        start = 0
        seen: set = set()

        while not self.should_stop:
            url = self._build_search_url(position, location, start)
            self.driver.get(url)
            time.sleep(2)

            cards = self._get_job_cards()
            if not cards:
                break

            for card in cards:
                if self.should_stop:
                    return

                meta = self._get_job_meta(card)
                job_id = meta.get("job_id", "")
                if job_id:
                    if job_id in seen:
                        continue
                    seen.add(job_id)

                if not self._is_easy_apply(card):
                    continue

                self._emit("job_applying", meta)
                try:
                    opened = self._click_apply(card)
                    submitted = self._fill_application() if opened else False
                    if submitted:
                        self.applied_count += 1
                        self._emit("job_applied", meta)
                    else:
                        self.failed_count += 1
                        self._emit("job_failed", meta)

                except NotImplementedError:
                    raise  # surface unimplemented scaffold immediately

                except Exception as e:
                    self.failed_count += 1
                    self._emit("job_failed", {**meta, "error": str(e)})

            # Paginate — stop when we get a partial page (last page)
            if len(cards) < self.RESULTS_PER_PAGE:
                break
            start += self.RESULTS_PER_PAGE
