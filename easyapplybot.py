import argparse
import asyncio
import json
import logging
import os
import random
import re
import threading
import time
import csv
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
try:
    import pyautogui
except ImportError:
    pyautogui = None  # type: ignore[assignment]
from fake_useragent import UserAgent
import requests
from openai import OpenAI
from dotenv import load_dotenv

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model matching Go's LinkedInProfile / ProfilePayload
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
    openai_api_key: str = ""
    blacklist: List[str] = []
    blacklist_titles: List[str] = []


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, event_type: str, data: Optional[dict] = None):
        message = json.dumps({"type": event_type, "data": data or {}})
        for ws in list(self.connections):
            try:
                await ws.send_text(message)
            except Exception:
                self.connections.remove(ws)


ws_manager = ConnectionManager()

# We need a reference to the running asyncio loop so the bot thread can
# schedule coroutines (broadcast) from its synchronous context.
_loop: Optional[asyncio.AbstractEventLoop] = None


def emit_event(event_type: str, data: Optional[dict] = None):
    """Thread-safe helper to broadcast a WebSocket event from any thread."""
    if _loop is None:
        return
    asyncio.run_coroutine_threadsafe(
        ws_manager.broadcast(event_type, data), _loop
    )


# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------

def setup_logger() -> None:
    dt = datetime.strftime(datetime.now(), "%m_%d_%y %H_%M_%S_")
    log_dir = os.path.join('.', 'logs')
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, dt + 'applyJobs.log'),
        filemode='w',
        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s',
        datefmt='%d-%b-%y %H:%M:%S',
    )
    log.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
    c_handler.setFormatter(c_format)
    log.addHandler(c_handler)


# ---------------------------------------------------------------------------
# EasyApplyBot  (refactored: accepts ProfileConfig, uses stop event)
# ---------------------------------------------------------------------------

class EasyApplyBot:
    MAX_SEARCH_TIME = 20 * 60 * 60

    def __init__(self, config: ProfileConfig) -> None:
        setup_logger()

        if config.openai_api_key:
            os.environ["OPENAI_API_KEY"] = config.openai_api_key
        else:
            load_dotenv()

        if not os.environ.get("OPENAI_API_KEY"):
            log.warning("OPENAI_API_KEY not set – LLM fallback will be disabled")

        log.info("Welcome to Easy Apply Bot")

        self._stop_event = threading.Event()
        self.applied_count = 0
        self.failed_count = 0
        self.total_seen = 0

        self.config = config
        self.phone_number = config.phone_number
        self.location = f"{config.user_city}, {config.user_state}" if config.user_city else ""
        self.years_of_experience = str(config.years_experience) if config.years_experience else ""
        self.desired_salary = str(config.desired_salary) if config.desired_salary else ""
        self.linkedin_profile_url = config.profile_url
        self.zip_code = config.zip_code
        self.user_state = config.user_state
        self.checked_invalid = False
        self.blacklist = [c.lower() for c in config.blacklist]
        self.blacklist_titles = [t.lower() for t in config.blacklist_titles]

        self.filename = "output.csv"
        past_ids = self.get_appliedIDs(self.filename)
        self.appliedJobIDs = past_ids if past_ids is not None else []

        # Setup Selenium driver
        self.browser = self._create_driver()
        self.wait = WebDriverWait(self.browser, 30)

    def _create_driver(self):
        ua = UserAgent()
        user_agent = ua.random
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features")
        options.add_argument(f'--user-agent={user_agent}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        return webdriver.Chrome(options=options)

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
    # CSV helpers
    # ------------------------------------------------------------------

    def get_appliedIDs(self, filename):
        try:
            df = pd.read_csv(
                filename, header=None,
                names=['timestamp', 'jobID', 'job', 'company', 'attempted', 'result'],
                lineterminator='\n', encoding='utf-8',
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], format="%Y-%m-%d %H:%M:%S")
            df = df[df['timestamp'] > (datetime.now() - timedelta(days=2))]
            jobIDs = list(df.jobID)
            log.info(f"{len(jobIDs)} jobIDs found")
            return jobIDs
        except Exception as e:
            log.info(f"{e}   jobIDs could not be loaded from CSV {filename}")
            return None

    # ------------------------------------------------------------------
    # LinkedIn login
    # ------------------------------------------------------------------

    def start_linkedin(self, username, password) -> bool:
        log.info("Logging in.....Please wait :)")
        self.browser.get("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
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
            emit_event("login_success")
            return True
        except TimeoutException:
            log.info("TimeoutException! Username/password field or login button not found")
            emit_event("login_failed", {"error": "Timeout finding login fields"})
            return False
        except Exception as e:
            emit_event("login_failed", {"error": str(e)})
            return False

    # ------------------------------------------------------------------
    # Main apply loop
    # ------------------------------------------------------------------

    def fill_data(self) -> None:
        try:
            self.browser.set_window_size(1, 1)
            self.browser.set_window_position(2000, 2000)
        except Exception as e:
            log.info(f"Could not set window size/position: {e}")

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
        count_job = 0
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

                self.load_page(sleep=2)
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

                if len(jobIDs) == 0 and len(IDs) > 23:
                    jobs_per_page += 25
                    count_job = 0
                    self.avoid_lock()
                    self.browser, jobs_per_page = self.next_jobs_page(position, location, jobs_per_page)

                for i, jobID in enumerate(jobIDs):
                    if self.stopped:
                        return

                    count_job += 1
                    self.get_job_page(jobID)

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
                    if self.blacklist and company.lower() in self.blacklist:
                        log.info(f"Skipping blacklisted company: {company}")
                        continue
                    if self.blacklist_titles and any(bt in job_title.lower() for bt in self.blacklist_titles):
                        log.info(f"Skipping blacklisted title: {job_title}")
                        continue

                    emit_event("job_applying", {"job_id": str(jobID), "title": job_title, "company": company})

                    button = self.get_easy_apply_button()

                    if button is not False:
                        log.info("Clicking the EASY apply button")
                        time.sleep(3)
                        result = self.send_resume()
                        count_application += 1
                        if result:
                            self.applied_count += 1
                            emit_event("job_applied", {"job_id": str(jobID), "title": job_title, "company": company})
                        else:
                            self.failed_count += 1
                            emit_event("job_failed", {"job_id": str(jobID), "title": job_title, "error": "submit failed"})
                    else:
                        log.info("The button does not exist.")
                        result = False

                    self.write_to_file(button, jobID, self.browser.title, result)
                    emit_event("progress", {
                        "applied": self.applied_count,
                        "failed": self.failed_count,
                        "total_seen": self.total_seen,
                    })

                    if count_application != 0 and count_application % 20 == 0:
                        sleepTime = random.randint(100, 300)
                        log.info(f"Time for a nap - see you in: {int(sleepTime / 60)} min")
                        time.sleep(sleepTime)

                    if count_job == len(jobIDs):
                        jobs_per_page += 25
                        count_job = 0
                        log.info("Going to next jobs page")
                        self.avoid_lock()
                        self.browser, jobs_per_page = self.next_jobs_page(position, location, jobs_per_page)

            except Exception as e:
                log.error(f"Exception in main application loop: {e}")
                emit_event("error", {"message": str(e)})

    # ------------------------------------------------------------------
    # Page / job helpers
    # ------------------------------------------------------------------

    def write_to_file(self, button, jobID, browserTitle, result) -> None:
        def re_extract(text, pattern):
            target = re.search(pattern, text)
            if target:
                target = target.group(1)
            return target

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attempted = False if button is False else True
        try:
            job = re_extract(browserTitle.split(' | ')[0], r"\(?\d?\)?\s?(\w.*)")
            company = re_extract(browserTitle.split(' | ')[1], r"(\w.*)")
        except Exception:
            job = "Unknown"
            company = "Unknown"

        toWrite = [timestamp, jobID, job, company, attempted, result]
        with open(self.filename, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(toWrite)

    def get_job_page(self, jobID):
        job = 'https://www.linkedin.com/jobs/view/' + str(jobID)
        self.browser.get(job)
        self.job_page = self.load_page(sleep=0.5)
        return self.job_page

    def get_easy_apply_button(self):
        try:
            button = self.browser.find_elements("xpath", '//*[contains(@aria-label, "Easy Apply to")]')
            if len(button) == 0:
                return False
            javascript = """
            let elements = Array.from(document.querySelectorAll('button[aria-label]'));
            let targetElement = elements.find(el => el.getAttribute('aria-label').includes('Easy Apply to'));
            if (targetElement) { targetElement.click(); }
            """
            self.browser.execute_script(javascript)
            time.sleep(1)
            return True
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

    def send_resume(self) -> bool:
        def is_present(button_locator) -> bool:
            return len(self.browser.find_elements(button_locator[0], button_locator[1])) > 0

        def has_errors() -> bool:
            return len(self.browser.find_elements(By.XPATH, '//*[contains(@type, "error-pebble-icon")]')) > 0

        try:
            time.sleep(random.uniform(1.5, 2.5))
            next_locater = (By.CSS_SELECTOR, "button[aria-label='Continue to next step']")
            review_locater = (By.CSS_SELECTOR, "button[aria-label='Review your application']")
            submit_locater = (By.CSS_SELECTOR, "button[aria-label='Submit application']")
            submit_application_locator = (By.CSS_SELECTOR, "button[aria-label='Submit application']")
            error_locator = (By.CLASS_NAME, "artdeco-inline-feedback__message")
            follow_locator = (By.CSS_SELECTOR, "label[for='follow-company-checkbox']")

            submitted = False
            while True:
                if self.stopped:
                    return False

                button = None
                buttons = [next_locater, review_locater, follow_locator,
                           submit_locater, submit_application_locator]
                for i, button_locator in enumerate(buttons):
                    if is_present(button_locator) and not has_errors():
                        button = self.wait.until(EC.element_to_be_clickable(button_locator))

                    if is_present(error_locator):
                        try:
                            for element in self.browser.find_elements(error_locator[0], error_locator[1]):
                                text = element.text
                                if ("Please enter" in text or "Please make" in text or "Enter a" in text or "Select checkbox to proceed") and not self.checked_invalid:
                                    self.fill_invalids()
                                    break
                        except Exception as e:
                            log.info(e)

                    if button:
                        button.click()
                        time.sleep(random.uniform(1.5, 2.5))
                        if i in (3, 4):
                            submitted = True
                        if i != 2:
                            break
                if submitted:
                    self.checked_invalid = False
                    log.info("Application Submitted")
                    try:
                        requests.get('https://api.pypes.dev/job-application')
                    except Exception as e:
                        log.info(f"{e} - cannot send job application to the api")
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
        if 'available' in label_lower or 'start' in label_lower or 'notice' in label_lower:
            return '2 weeks'
        if any(keyword in label_lower for keyword in ['skill', 'technology', 'programming', 'language']):
            return 'Python, JavaScript, SQL'
        if any(keyword in label_lower for keyword in ['education', 'degree', 'university', 'college']):
            return 'Bachelor'
        if any(keyword in label_lower for keyword in ['linkedin', 'linked-in', 'linked in']):
            return self.linkedin_profile_url

        if input_type == "text":
            llm_answer = self.get_llm_suggested_answer(label_text, input_type)
            if llm_answer:
                return llm_answer
            return '3'

        return ''

    def fill_invalids(self):
        try:
            location = self.browser.find_element(By.CSS_SELECTOR, "input[id*='GEO-LOCATION']")
        except Exception:
            location = None

        if location:
            location.send_keys(self.location)
            try:
                dropdown_option = WebDriverWait(self.browser, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//div[contains(@class, 'basic-typeahead__selectable')]//span[contains(@class, 'search-typeahead-v2__hit-text')]"
                    ))
                )
                dropdown_option.click()
            except Exception:
                pass
            return

        try:
            your_name_label = self.browser.find_element(By.XPATH, "//label[contains(text(), 'Your Name')]")
            input_id = your_name_label.get_attribute('for')
            input_element = self.browser.find_element(By.ID, input_id)
            input_element.clear()
            # Use email username as a fallback name
            name = self.config.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
            input_element.send_keys(name)
        except Exception as e:
            log.error(f"Error finding your name label: {e}")

        text_inputs = self.browser.find_elements(By.XPATH, '//input[contains(@class, "fb-dash-form-element")]')
        for input_element in text_inputs:
            try:
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

        radio_inputs = self.browser.find_elements(By.XPATH, '//input[@data-test-text-selectable-option__input="Yes"]')
        for input_element in radio_inputs:
            try:
                question_text = self.get_radio_question_text(input_element)
                question_lower = question_text.lower()
                if any(keyword in question_lower for keyword in ['visa', 'sponsor', 'work authorization', 'citizen']):
                    no_input = self.browser.find_element(By.XPATH, '//input[@data-test-text-selectable-option__input="No"]')
                    if no_input:
                        loc = no_input.location
                        element_to_click = self.browser.execute_script(
                            "return document.elementFromPoint(arguments[0], arguments[1]);",
                            loc['x'], loc['y'])
                        element_to_click.click()
                        log.info(f"Selected 'No' for visa-related question: {question_text}")
                        continue
                loc = input_element.location
                element_to_click = self.browser.execute_script(
                    "return document.elementFromPoint(arguments[0], arguments[1]);",
                    loc['x'], loc['y'])
                element_to_click.click()
                log.info(f"Selected 'Yes' for question: {question_text}")
            except Exception as e:
                log.error(f"Error handling radio button: {e}")
                try:
                    loc = input_element.location
                    element_to_click = self.browser.execute_script(
                        "return document.elementFromPoint(arguments[0], arguments[1]);",
                        loc['x'], loc['y'])
                    element_to_click.click()
                except Exception:
                    pass
        time.sleep(1)

        try:
            select_inputs = self.browser.find_elements(By.CSS_SELECTOR, 'select[aria-required="true"]')
            for inp in select_inputs:
                question_text = self.get_select_question_text(inp)
                question_lower = question_text.lower()
                log.info(f"Select input question: {question_text}")
                select_obj = Select(inp)
                options = select_obj.options
                for option in options:
                    ot = option.text.lower()
                    if "united states" in ot:
                        select_obj.select_by_visible_text(option.text)
                        log.info(f"Selected option '{option.text}' for question: {question_text}")
                    elif "immediate family" in question_lower and "no" in ot:
                        select_obj.select_by_visible_text(option.text)
                        log.info(f"Selected option '{option.text}' for question: {question_text}")
                    elif "no" in ot and "require" in question_lower:
                        select_obj.select_by_visible_text(option.text)
                        log.info(f"Selected option '{option.text}' for question: {question_text}")
                    elif ("yes" in ot and "do you require" not in question_lower) or "native" in ot or "U.S." in ot or "us" in ot or "linkedin" in ot or "united states" in ot or "citizen" in ot:
                        select_obj.select_by_visible_text(option.text)
                        log.info(f"Selected option '{option.text}' for question: {question_text}")
        except Exception as e:
            log.error(f'error doing select inputs: {e}')

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
                    textarea.clear()
                    textarea.send_keys('3')
                    log.info(f"Filled textarea '{label_text}' with default value: 3")
            except Exception as e:
                log.error(f"Error filling textarea field: {e}")
                try:
                    textarea.clear()
                    textarea.send_keys('3')
                except Exception:
                    pass

    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 4000:
            self.browser.execute_script("window.scrollTo(0," + str(scroll_page) + " );")
            scroll_page += 200
            time.sleep(sleep)
        if sleep != 1:
            self.browser.execute_script("window.scrollTo(0,0);")
            time.sleep(sleep * 3)
        page = BeautifulSoup(self.browser.page_source, "lxml")
        return page

    def avoid_lock(self) -> None:
        if pyautogui is None:
            return
        try:
            pyautogui.FAILSAFE = False
            x, _ = pyautogui.position()
            pyautogui.moveTo(x + 200, pyautogui.position().y, duration=1.0)
            pyautogui.moveTo(x, pyautogui.position().y, duration=0.5)
            time.sleep(0.5)
            pyautogui.press('esc')
        except Exception as e:
            # pyautogui requires a display server (X11/Wayland on Linux,
            # Quartz on macOS). Skip mouse jiggle if unavailable.
            log.debug(f"avoid_lock skipped (no display?): {e}")

    def next_jobs_page(self, position, location, jobs_per_page):
        self.browser.get(
            "https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords=" +
            position + location + "&sortBy=DD&start=" + str(jobs_per_page))
        self.avoid_lock()
        log.info("Lock avoided.")
        self.load_page()
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

    def get_llm_suggested_answer(self, label_text, input_type="text"):
        try:
            openai_api_key = os.environ.get("OPENAI_API_KEY")
            if not openai_api_key:
                return ""
            client = OpenAI(api_key=openai_api_key)
            name = self.config.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
            positions_str = ', '.join(self.config.positions) if self.config.positions else "Software Engineer"
            location_str = self.location or "United States"
            yoe = self.years_of_experience or "3"
            salary = self.desired_salary or "100000"
            prompt = (
                f"You are {name}, a professional applying for jobs as a {positions_str} "
                f"based in {location_str} with {yoe} years of experience. "
                f"Provide a short, succinct, professional answer for the following job application question: "
                f"'{label_text}'. If it asks for numerics such as years of experience or hourly wage, "
                f"answer with a numeric digit response: {yoe} for years of experience, and {salary} for salary."
            )
            response = client.responses.create(
                model="gpt-4o",
                instructions=prompt,
                input=label_text,
            )
            answer = response.output_text.strip()
            log.info(f"LLM suggested answer for '{label_text}': {answer}")
            return answer
        except Exception as e:
            log.error(f"OpenAI LLM request failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Bot runner state (module-level so FastAPI endpoints can access it)
# ---------------------------------------------------------------------------

_bot: Optional[EasyApplyBot] = None
_bot_thread: Optional[threading.Thread] = None
_bot_lock = threading.Lock()
_applying = False


def _run_bot(config: ProfileConfig):
    """Target function for the bot background thread."""
    global _bot, _applying
    try:
        _bot = EasyApplyBot(config)

        if not _bot.start_linkedin(config.email, config.password):
            emit_event("bot_stopped", {"reason": "login_failed"})
            _bot.close()
            _bot = None
            _applying = False
            return

        emit_event("bot_started")
        _applying = True

        positions = [p for p in config.positions if p]
        locations = [loc for loc in config.locations if loc]

        if not positions or not locations:
            emit_event("bot_stopped", {"reason": "no positions or locations configured"})
            _bot.close()
            _bot = None
            _applying = False
            return

        _bot.start_apply(positions, locations)
        emit_event("bot_stopped", {"reason": "completed"})
    except Exception as e:
        log.error(f"Bot thread exception: {e}")
        emit_event("error", {"message": str(e)})
        emit_event("bot_stopped", {"reason": f"error: {e}"})
    finally:
        if _bot:
            _bot.close()
            _bot = None
        _applying = False


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    yield
    # Shutdown: stop bot if running
    with _bot_lock:
        if _bot:
            _bot.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    return {
        "running": _bot is not None,
        "applying": _applying,
        "applied_count": _bot.applied_count if _bot else 0,
        "failed_count": _bot.failed_count if _bot else 0,
    }


@app.post("/start")
async def start(config: ProfileConfig):
    global _bot_thread
    with _bot_lock:
        if _bot is not None:
            return {"error": "bot already running"}

        _bot_thread = threading.Thread(target=_run_bot, args=(config,), daemon=True)
        _bot_thread.start()

    return {"status": "starting"}


@app.post("/stop")
async def stop():
    global _bot, _bot_thread, _applying
    with _bot_lock:
        if _bot is None:
            return {"status": "not running"}
        _bot.stop()

    # Wait for thread to finish
    if _bot_thread and _bot_thread.is_alive():
        _bot_thread.join(timeout=10)

    # Force close if still around
    with _bot_lock:
        if _bot:
            _bot.close()
            _bot = None
        _applying = False

    return {"status": "stopped"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep connection alive; we mainly send events *to* Go
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EasyApplyBot FastAPI server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
