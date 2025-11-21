import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timedelta, timezone
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

# Define Brisbane Timezone explicitly (UTC+10)
BRISBANE_TZ = timezone(timedelta(hours=10))

# --- CSS SELECTORS ---
EVENT_CONTAINER_SELECTOR = 'a[href^="https://thegabba.com.au/events/"][target="_self"]'
EVENT_TITLE_SELECTOR = 'h3.text-h4'
EVENT_DATE_BLOCK_SELECTOR = 'div.top-4.absolute.left-0'
EVENT_TIME_SELECTORS = 'div.text-h6'
# ---------------------

def get_page_source_with_selenium():
    """
    Uses a headless Chrome browser (Selenium) to load the page,
    continually clicks 'See more', and returns the full HTML.
    """
    print("Setting up headless Chrome browser...", flush=True)
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox") 
    chrome_options.add_argument("--disable-dev-shm-usage") 
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print(f"Fetching {EVENTS_URL} with Selenium...", flush=True)
        driver.get(EVENTS_URL)

        print("Waiting 10s for initial load...", flush=True)
        time.sleep(10)

        # --- CLICK "SEE MORE" LOOP ---
        # Try to click up to 10 times to load all future events
        for i in range(10):
            try:
                print(f"Checking for 'See more' button (Attempt {i+1})...", flush=True)
                
                # Scroll to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

                # Look for an element with text "See more"
                load_more_button = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'See more')]"))
                )
                
                # Force click with JavaScript
                print("Button found. Clicking...", flush=True)
                driver.execute_script("arguments[0].click();", load_more_button)
                
                # Wait for new items to populate
                time.sleep(4)
                
            except Exception:
                print("No 'See more' button found (or end of list reached).", flush=True)
                break
        # -----------------------------

        print("All events loaded. Getting page source.", flush=True)
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
    
    event_elements = soup.select(EVENT_CONTAINER_SELECTOR)
    
    if not event_elements:
        print(f"Warning: No elements found with selector '{EVENT_CONTAINER_SELECTOR}'.", flush=True)
        return []

    print(f"Found {len(event_elements)} event elements. Parsing...", flush=True)

    for event in event_elements:
        try:
            # 1. Get Title
            title_element = event.select_one(EVENT_TITLE_SELECTOR)
            title = title_element.text.strip() if title_element else "Unknown Event"

            # 2. Get URL
            url = event['href']

            # 3. Get Date
            date_block = event.select_one(EVENT_DATE_BLOCK_SELECTOR)
            date_parts = date_block.find_all('div') if date_block else []
            
            if len(date_parts) >= 3:
                day_str = date_parts[0].text.strip() 
                day_num = date_parts[1].text.strip() 
                month_str = date_parts[2].text.strip() 
                
                # --- LOGIC UPDATE: YEAR HANDLING ---
                current_now = datetime.now()
                year_to_use = current_now.year
                
                # Construct a temporary date string using the CURRENT year
                temp_date_str = f"{day_num} {month_str} {year_to_use}"
                
                try:
                    # Parse strictly to check "age"
                    temp_date = parse_date(temp_date_str)
                    
                    # Calculate 30 days ago from right now
                    thirty_days_ago = current_now - timedelta(days=30)
                    
                    # If the event date (with current year) is OLDER than 30 days ago,
                    # it implies this event is actually for next year.
                    # Example: It's Nov 2025. We parse "Jan 15". 
                    # Jan 15 2025 is < Oct 2025. So we bump year to 2026.
                    if temp_date < thirty_days_ago:
                        year_to_use += 1
                        
                except ValueError:
                    pass # Keep current year if parsing check fails slightly
                
                # Final date string with the correct year
                date_string = f"{day_num} {month_str} {year_to_use}"
                # -----------------------------------

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
                    
                    if not start_time_str and "gates open" in time_desc.lower() and time_val != "TBC":
                        start_time_str = time_val
            
            # Fallback time
            if not start_time_str:
                for line in description_lines:
                    time_val = line.split(' - ')[0]
                    if time_val != "TBC":
                        start_time_str = time_val
                        break

            # 5. Combine Date and Time
            full_datetime_str = date_string
            is_all_day = True
            if start_time_str:
                try:
                    test_dt = parse_date(start_time_str)
                    full_datetime_str = f"{date_string} {start_time_str}"
                    is_all_day = False
                except ValueError:
                    print(f"Warning: Could not parse time '{start_time_str}'. Defaulting to all-day.", flush=True)
            
            # --- TIMEZONE FIX ---
            # 1. Parse the string (creates a naive datetime)
            start_datetime = parse_date(full_datetime_str)
            
            # 2. Force the object to be Brisbane Time
            start_datetime = start_datetime.replace(tzinfo=BRISBANE_TZ)
            # --------------------

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
        
        # Convert Brisbane time to UTC for the .ics file
        start_dt_utc = event['start_datetime'].astimezone(timezone.utc)
        
        ievent.add('dtstart', start_dt_utc)
        
        if not event['is_all_day']:
            # Calculate end time (Brisbane + 3 hours), then convert to UTC
            end_dt_brisbane = event['start_datetime'] + timedelta(hours=3)
            end_dt_utc = end_dt_brisbane.astimezone(timezone.utc)
            ievent.add('dtend', end_dt_utc)
        
        ievent.add('dtstamp', datetime.now(timezone.utc))
        ievent.add('location', 'The Gabba, Vulture St, Woolloongabba QLD 4102')
        ievent.add('description', f"{event['description']}\n\nMore info: {event['url']}")
        ievent.add('url', event['url'])
        ievent.add('uid', f"{event['start_datetime'].isoformat()}@{event['url']}")
        
        cal.add_component(ievent)

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
    
    if os.getenv('GITHUB_WORKSPACE'):
        os.chdir(os.getenv('GITHUB_WORKSPACE'))
        print(f"Running in GITHUB_WORKSPACE: {os.getcwd()}", flush=True)
    
    html_content = get_page_source_with_selenium()
    
    if html_content:
        events = scrape_gabba_events(html_content)
        if events:
            create_ical_file(events)
        else:
            print("No events found or parsed.", flush=True)
            sys.exit(1)
    else:
        print("Failed to get page source.", flush=True)
        sys.exit(1)
    
    print("Script finished.", flush=True)
