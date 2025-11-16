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
    print("Setting up headless Chrome browser...", flush=True)
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
        print(f"Fetching {EVENTS_URL} with Selenium...", flush=True)
        driver.get(EVENTS_URL)

        # --- NEW STRATEGY ---
        # The WebDriverWait is failing, even though the error log shows the element
        # exists. This suggests a race condition with the Vue.js app.
        # We will replace the "smart" wait with a longer "dumb" wait.
        print("Waiting 15s for dynamic content to load...", flush=True)
        time.sleep(15)
        # --------------------

        print("Events should be loaded. Getting page source.", flush=True)
        # Scroll down a bit to trigger any lazy-loading, just in case
        driver.execute_script("window.scrollTo(0, 1000);")
        time.sleep(2) # Give it a moment

        return driver.page_source

    except Exception as e:
        print(f"Error during Selenium page load: {e}", flush=True)
        if driver:
            print("Page source at time of error:", driver.page_source, flush=True)
        return None
    finally:
        if driver:
            driver.quit()
            print("Browser closed.", flush=True)

def save_html_for_debugging(html_content):
    """
    Saves the retrieved HTML to a file for debugging.
    Assumes we are already in the correct working directory (from os.chdir in main).
    """
    if not html_content:
        print("No HTML content to save.", flush=True)
        return
        
    try:
        # We've already os.chdir()'d in main, so just use the relative path
        with open(DEBUG_HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(html_content)
        # Print the absolute path to confirm where it was saved
        print(f"Successfully saved debug HTML to {os.path.abspath(DEBUG_HTML_FILE)}", flush=True)
    except Exception as e:
        print(f"Error saving debug HTML: {e}", flush=True)

def scrape_gabba_events(html_content):
    """
    Takes the full HTML content from Selenium and parses it.
    """
    print("Parsing HTML...", flush=True)
    if not html_content:
        print("Error: No HTML content provided to parser.", flush=True)
        return []
    
    events = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all event containers
    event_elements = soup.select(EVENT_CONTAINER_SELECTOR)
    
    if not event_elements:
        print(f"Warning: No elements found with selector '{EVENT_CONTAINER_SELECTOR}'.", flush=True)
        print("This means the website's HTML structure has changed OR we are being blocked.", flush=True)
        return []

    print(f"Found {len(event_elements)} event elements. Parsing...", flush=True)

    for event in event_elements:
        try:
            # 1. Get Title
            title_element = event.select_one(EVENT_TITLE_SELECTOR)
            title = title_element.text.strip() if title_element else "Unknown Event"

            # 2. Get URL
            url = event['href']
            if not url.startswith('http'):
                url = f"https://thegabba.com.au{url}"

            # 3. Get Date
            date_block = event.select_one(EVENT_DATE_BLOCK_SELECTOR)
            date_parts = date_block.find_all('div') if date_block else []
            
            if len(date_parts) >= 3:
                day_str = date_parts[0].text.strip() # "Sat"
                day_num = date_parts[1].text.strip() # "22"
                month_str = date_parts[2].text.strip() # "Nov"
                # We need to add the current year, as it's not on the page
                current_year = datetime.now().year
                date_string = f"{day_num} {month_str} {current_year}"
                
                # Check if the event is in the past (e.g., Dec event in Jan)
                parsed_date_check = parse_date(date_string)
                if parsed_date_check < datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) and datetime.now().month == 1:
                     date_string = f"{day_num} {month_str} {current_year + 1}"

            else:
                print(f"Warning: Could not parse date for event: {title}", flush=True)
                continue

            # 4. Get Time and Description
            time_elements = event.select(EVENT_TIME_SELECTORS)
            description_lines = []
            start_time_str = None
            
            for time_element in time_elements:
                time_spans = time_element.find_all('span')
                if len(time_spans) == 2:
                    time_val = time_spans[0].text.strip()
                    time_desc = time_spans[1].text.strip()
                    description_lines.append(f"{time_val} - {time_desc}")
                    
                    # Try to use the first valid time as the start time
                    if not start_time_str and time_val != "TBC":
                        start_time_str = time_val

            # 5. Combine Date and Time
            full_datetime_str = date_string
            is_all_day = True
            if start_time_str:
                try:
                    # This will parse "1:30pm" correctly
                    test_dt = parse_date(start_time_str)
                    full_datetime_str = f"{date_string} {start_time_str}"
                    is_all_day = False
                except ValueError:
                    print(f"Warning: Could not parse time '{start_time_str}'. Defaulting to all-day.", flush=True)
                    
            start_datetime = parse_date(full_datetime_str)

            events.append({
                'title': title,
                'start_datetime': start_datetime,
                'is_all_day': is_all_day,
                'description': "\n".join(description_lines),
                'url': url
            })

        except Exception as e:
            print(f"--- ERROR PARSING ONE EVENT ---", flush=True)
            print(f"Error: {e}", flush=True)
            print(f"Problematic HTML snippet: {event}", flush=True)
            print("---------------------------------", flush=True)
            
    return events

def create_ical_file(events):
    """
    Creates an iCalendar file from the list of events.
    """
    print(f"Creating iCal file with {len(events)} events...", flush=True)
    cal = Calendar()
    cal.add('prodid', '-//Gabba Event Scraper//thegabba.com.au//')
    cal.add('version', '2.0')
    cal.add('name', 'The Gabba Events')
    cal.add('X-WR-CALNAME', 'The Gabba Events')
    cal.add('description', 'Events at The Gabba, scraped from the official website.')
    cal.add('X-WR-CALDESC', 'Events at The Gabba, scraped from the official website.')

    for event in events:
        ievent = Event()
        ievent.add('summary', event['title'])
        
        # Add timezone info (Australia/Brisbane)
        ievent.add('dtstart', event['start_datetime'], parameters={'TZID': 'Australia/Brisbane'})
        
        if not event['is_all_day']:
            # Add an end time (assuming 2 hours for now, can be adjusted)
            ievent.add('dtend', event['start_datetime'] + timedelta(hours=2), parameters={'TZID': 'Australia/Brisbane'})
        
        ievent.add('dtstamp', datetime.now())
        ievent.add('location', 'The Gabba, Vulture St, Woolloongabba QLD 4102')
        ievent.add('description', f"{event['description']}\n\nMore info: {event['url']}")
        ievent.add('url', event['url'])
        ievent.add('uid', f"{event['start_datetime'].isoformat()}@{event['url']}")
        
        cal.add_component(ievent)

    # Save the file
    workspace = os.getenv('GITHUB_WORKSPACE', '.')
    output_path = os.path.join(workspace, OUTPUT_FILE)
    try:
        with open(output_path, 'wb') as f:
            f.write(cal.to_ical())
        print(f"Successfully created iCal file at {output_path}", flush=True)
    except Exception as e:
        print(f"Error writing iCal file: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    print("--- Gabba iCal Scraper (Selenium Method) ---", flush=True)
    
    # Set the working directory for the GitHub Action
    # This ensures the output file is created in the repo root
    if os.getenv('GITHUB_WORKSPACE'):
        os.chdir(os.getenv('GITHUB_WORKSPACE'))
        print(f"Running in GITHUB_WORKSPACE: {os.getcwd()}", flush=True)
    
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
            print("No events found or parsed, iCal file was not updated.", flush=True)
            sys.exit(1) # Exit with error
    else:
        print("Failed to get page source with Selenium. Aborting.", flush=True)
        sys.exit(1) # Exit with error
    
    print("Script finished.", flush=True)
