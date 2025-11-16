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

        # Let's give the page a simple 5 seconds to settle *before*
        # we start probing it with WebDriverWait. This adds stability.
        print("Waiting 5s for JavaScript to settle...")
        time.sleep(5)

        # THIS IS THE KEY: Wait for up to 30 seconds for the FIRST event
        # to appear. This ensures the JavaScript has finished running.
        print(f"Waiting for events to load (max 30s)... Selector: {EVENT_CONTAINER_SELECTOR}")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, EVENT_CONTAINER_SELECTOR))
        )

        print("Events found! Getting page source.")
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


def scrape_gabba_events(html_content):
    """
    Takes the full HTML content from Selenium and parses it.
    """
    if not html_content:
        print("Error: No HTML content provided to parser.")
        return []

    print("Parsing HTML...")
    soup = BeautifulSoup(html_content, 'html.parser')
    
    events = []
    # Select all event containers
    event_elements = soup.select(EVENT_CONTAINER_SELECTOR)
    
    if not event_elements:
        print(f"Warning: No elements found with selector '{EVENT_CONTAINER_SELECTOR}'.")
        print("This means the website's HTML structure has changed and the script needs updating.")
        return []

    print(f"Found {len(event_elements)} event elements. Parsing each event...")

    for event_html in event_elements:
        try:
            # --- Extract Title ---
            title_element = event_html.select_one(EVENT_TITLE_SELECTOR)
            title = title_element.text.strip() if title_element else "Unknown Event"
            
            # --- Extract URL ---
            href = event_html.get('href')
            url = f"https://thegabba.com.au{href}" if href else EVENTS_URL
            
            # --- Extract Date ---
            date_block = event_html.select_one(EVENT_DATE_BLOCK_SELECTOR)
            if not date_block:
                print(f"Warning: Skipping event '{title}' - could not find date block.")
                continue
                
            # Filter out the hidden "TBC" div by selecting only those *without* that style
            date_parts = [div.text.strip() for div in date_block.select('div') if 'display: none' not in div.get('style', '')]
            
            if len(date_parts) < 3:
                print(f"Warning: Skipping event '{title}' - date block format was unexpected: {date_parts}")
                continue
            
            # e.g., date_string = "Sat 22 Nov"
            date_string = f"{date_parts[0]} {date_parts[1]} {date_parts[2]}"
            
            # --- Extract Time & Description ---
            time_rows = event_html.select(EVENT_TIME_SELECTORS)
            time_string = None
            description_lines = []
            
            for row in time_rows:
                spans = row.select('span')
                if len(spans) == 2:
                    time_val = spans[0].text.strip()
                    time_desc = spans[1].text.strip()
                    description_lines.append(f"{time_desc}: {time_val}")
                    
                    # Try to set the *first* time found as the event start time
                    if not time_string:
                        time_string = time_val

            # Build a full string for the parser, e.g., "Sat 22 Nov 1:30pm"
            # We add the current year to help the parser
            current_year = datetime.now().year
            full_date_string = f"{date_string} {current_year} {time_string}" if time_string else f"{date_string} {current_year}"
            
            # --- Parse Date/Time ---
            try:
                event_date = parse_date(full_date_string)
                # Mark as all-day if we couldn't find a time
                is_all_day = (time_string is None)
            except Exception as e:
                print(f"Warning: Could not parse date string '{full_date_string}'. Skipping '{title}'. Error: {e}")
                continue

            events.append({
                'title': title,
                'start_date': event_date,
                'is_all_day': is_all_day,
                'description': "\n".join(description_lines), # e.g. "Gates open: 1:30pm\nFirst Ball: 2:00pm"
                'url': url
            })

        except Exception as e:
            print(f"Error parsing an event element: {e}. Skipping.")
            
    print(f"Successfully parsed {len(events)} events.")
    return events


def create_ical_file(events):
    """
    Takes a list of event dicts and writes them to an .ics file.
    """
    print(f"Creating iCalendar file: {OUTPUT_FILE}...")
    cal = Calendar()
    cal.add('prodid', '-//Gabba Event Scraper//YOUR_USERNAME//')
    cal.add('version', '2.0')
    cal.add('name', 'The Gabba Events')
    cal.add('X-WR-CALNAME', 'The Gabba Events')
    cal.add('description', 'Events at The Gabba, scraped from the official website.')
    # Set the calendar's timezone
    cal.add('X-WR-TIMEZONE', 'Australia/Brisbane')

    for event_data in events:
        event = Event()
        event.add('summary', event_data['title'])
        
        if event_data['is_all_day']:
            # Set as an all-day event
            event.add('dtstart', event_data['start_date'].date())
        else:
            # Set as a specific time. The datetime object is timezone-naive,
            # but the calendar's X-WR-TIMEZONE will tell clients (like Google)
            # how to interpret this time.
            event.add('dtstart', event_data['start_date'])
        
        full_description = f"{event_data['description']}\n\nMore info: {event_data['url']}"
        event.add('description', full_description)
        event.add('location', 'The Gabba, Vulture St, Woolloongabba QLD 4102, Australia')
        event.add('url', event_data['url'])
        
        # Create a unique ID
        uid = f"{event_data['start_date'].strftime('%Y%m%d')}-{event_data['url'].split('/')[-1]}@thegabba.com.au"
        event.add('uid', uid)
        
        cal.add_component(event)

    try:
        # Get the full output path using GITHUB_WORKSPACE if available
        workspace = os.getenv('GITHUB_WORKSPACE', '.')
        output_path = os.path.join(workspace, OUTPUT_FILE)
        
        with open(output_path, 'wb') as f:
            f.write(cal.to_ical())
        print(f"Successfully wrote {len(events)} events to {output_path}")
    except IOError as e:
        print(f"Error: Could not write to file {output_path}. {e}")
        sys.exit(1) # Exit with an error code
    except Exception as e:
        print(f"An unexpected error occurred during file writing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("--- Gabba iCal Scraper (Selenium Method) ---")
    
    # Set the working directory for the GitHub Action
    # This ensures the output file is created in the repo root
    if os.getenv('GITHUB_WORKSPACE'):
        os.chdir(os.getenv('GITHUB_WORKSPACE'))
        print(f"Running in GITHUB_WORKSPACE: {os.getcwd()}")
    
    # 1. Get the full HTML source using Selenium
    html_content = get_page_source_with_selenium()
    
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
