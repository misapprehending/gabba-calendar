import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime
from dateutil.parser import parse as parse_date
import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# --- CONFIGURATION ---
EVENTS_URL = "https://thegabba.com.au/whats-on"
OUTPUT_FILE = "gabba-events.ics"
DEBUG_HTML_FILE = "debug_page.html" # New file for debugging

# --- THESE ARE THE CORRECT, VERIFIED CSS SELECTORS (from your HTML) ---

# This selector is used to WAIT for the page to finish loading.
# We will wait until the browser has rendered at least one event link.
EVENT_CONTAINER_SELECTOR = 'a[href^="/events/"][target="_self"]'

# Selects the event title
EVENT_TITLE_SELECTOR = 'h3.text-h4'

# Selects the container for the date (Day, Num, Month)
EVENT_DATE_BLOCK_SELECTOR = 'div.top-4.absolute.left-0'

# Selects all rows of event times (e.g., "Gates open", "First Ball")
EVENT_TIME_SELECTORS = 'div.text-h6'

# ---------------------------------------------------

def get_page_source_with_selenium():
    """
    Uses a headless Chrome browser (Selenium) to load the page,
    wait for JavaScript to render the events, and then returns the
    full page's HTML source.
    """
    print("Setting up headless Chrome browser...")
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Run without a GUI
    chrome_options.add_argument("--no-sandbox") # Required for GitHub Actions
    chrome_options.add_argument("--disable-dev-shm-usage") # Required for GitHub Actions
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # --- THIS IS THE FIX ---
    # This hides the "navigator.webdriver" flag that websites use to detect Selenium
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # -----------------------

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print(f"Fetching {EVENTS_URL} with Selenium...")
        driver.get(EVENTS_URL)

        # --- NEW STRATEGY ---
        # The WebDriverWait is failing, even though the error log shows the element
        # exists. This suggests a race condition with the Vue.js app.
        # We will replace the "smart" wait with a longer "dumb" wait.
        print("Waiting 15s for dynamic content to load...")
        time.sleep(15)
        # --------------------

        print("Events should be loaded. Getting page source.")
        # Scroll down a bit to trigger any lazy-loading, just in case
        driver.execute_script("window.scrollTo(0, 1000);")
        time.sleep(2) # Give it a moment

        return driver.page_source

    except Exception as e:
        print(f"Error during Selenium page load: {e}")
        if driver:
            print("Page source at time of error:", driver.page_source)
        return None
    finally:
        if driver:
            driver.quit()
            print("Browser closed.")

def save_html_for_debugging(html_content):
    """
    Saves the retrieved HTML to a file for debugging.
    """
    if not html_content:
        print("No HTML content to save.")
        return
        
    workspace = os.getenv('GITHUB_WORKSPACE', '.')
    output_path = os.path.join(workspace, DEBUG_HTML_FILE)
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Successfully saved debug HTML to {output_path}")
    except Exception as e:
        print(f"Error saving debug HTML: {e}")

def scrape_gabba_events(html_content):
    """
    Takes the full HTML content from Selenium and parses it.
    """
# ... (rest of the function is identical to the file) ...
    if not html_content:
        print("Error: No HTML content provided to parser.")
# ... (rest of the function is identical to the file) ...
    event_elements = soup.select(EVENT_CONTAINER_SELECTOR)
    
    if not event_elements:
# ... (rest of the function is identical to the file) ...
# ... (rest of the file is identical) ...
if __name__ == "__main__":
    print("--- Gabba iCal Scraper (Selenium Method) ---")
    
    # Set the working directory for the GitHub Action
    # This ensures the output file is created in the repo root
    if os.getenv('GITHUB_WORKSPACE'):
        os.chdir(os.getenv('GITHUB_WORKSPACE'))
        print(f"Running in GITHUB_WORKSPACE: {os.getcwd()}")
    
    # 1. Get the full HTML source using Selenium
    html_content = get_page_source_with_selenium()
    
    # --- NEW DEBUG STEP ---
    # Save the HTML we got from Selenium so we can inspect it.
    save_html_for_debugging(html_content)
    # ----------------------

    if html_content:
        # 2. Parse the HTML
        events = scrape_gabba_events(html_content)
        
        if events:
            # 3. Create the file
            create_ical_file(events)
        else:
            print("No events found or parsed, iCal file was not updated.")
            sys.exit(1) # Exit with error
    else:
        print("Failed to get page source with Selenium. Aborting.")
        sys.exit(1) # Exit with error
    
    print("Script finished.")
