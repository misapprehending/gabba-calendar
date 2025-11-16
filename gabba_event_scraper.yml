import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime
from dateutil.parser import parse as parse_date
import os

# --- CONFIGURATION ---
# This is the URL we are scraping
EVENTS_URL = "https://thegabba.com.au/whats-on"

# This is the file your script will create
OUTPUT_FILE = "gabba-events.ics"

# --- IMPORTANT: UPDATE THESE SELECTORS ---
# You must find these values by inspecting the page in your browser
# (Right-click on an event -> "Inspect")
#
# This selector should target the main container for a single event.
# e.g., '.event-list-item' or 'div.card'
EVENT_CONTAINER_SELECTOR = 'div.event-item'

# These selectors are relative to the event container above
# e.g., 'h3.event-title' or '.event-details a'
EVENT_TITLE_SELECTOR = 'h3.summary'
EVENT_DATE_SELECTOR = 'span.event-date' # A selector for the element with the date text
EVENT_URL_SELECTOR = 'a.event-link' # A selector for the event's "details" link
EVENT_DESCRIPTION_SELECTOR = 'p.description' # (Optional) selector for a short description
# ----------------------------------------


def scrape_gabba_events():
    """
    Fetches event data from The Gabba website and returns a list of dicts.
    """
    print(f"Fetching events from {EVENTS_URL}...")
    
    headers = {
        'User-Agent': 'Gabba-iCal-Scraper (https-github-com/YOUR_USERNAME/YOUR_REPO)'
    }
    
    try:
        response = requests.get(EVENTS_URL, headers=headers)
        response.raise_for_status()  # Raises an error for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not fetch URL. {e}")
        return []

    print("Successfully fetched page. Parsing HTML...")
    soup = BeautifulSoup(response.text, 'html.parser')
    
    events = []
    event_elements = soup.select(EVENT_CONTAINER_SELECTOR)
    
    if not event_elements:
        print(f"Warning: No elements found with selector '{EVENT_CONTAINER_SELECTOR}'.")
        print("Please update the CSS selectors in the script.")
        return []

    print(f"Found {len(event_elements)} event elements. Parsing each event...")

    for event_html in event_elements:
        try:
            # --- Extract Data ---
            # Use .text.strip() to get the clean text from an element
            
            title_element = event_html.select_one(EVENT_TITLE_SELECTOR)
            title = title_element.text.strip() if title_element else None
            
            date_element = event_html.select_one(EVENT_DATE_SELECTOR)
            date_string = date_element.text.strip() if date_element else None
            
            url_element = event_html.select_one(EVENT_URL_SELECTOR)
            # Make URL absolute if it's relative (e.g., /events/foo)
            if url_element and url_element.get('href'):
                if url_element['href'].startswith('/'):
                    url = f"https://thegabba.com.au{url_element['href']}"
                else:
                    url = url_element['href']
            else:
                url = EVENTS_URL
            
            desc_element = event_html.select_one(EVENT_DESCRIPTION_SELECTOR)
            description = desc_element.text.strip() if desc_element else title

            # --- Clean and Validate ---
            if not title or not date_string:
                print("Warning: Skipping an event due to missing title or date.")
                continue

            # Parse the date string (e.g., "Sun 23 Nov") into a datetime object
            # dateutil.parser is very flexible and can handle most formats.
            try:
                # We assume the event is this year. 
                # This parser is smart, but might need hints if the date is ambiguous
                event_date = parse_date(date_string)
            except Exception as e:
                print(f"Warning: Could not parse date string '{date_string}'. Skipping. Error: {e}")
                continue

            events.append({
                'title': title,
                'start_date': event_date,
                'description': description,
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
    cal.add('X-WR-TIMEZONE', 'Australia/Brisbane')

    for event_data in events:
        event = Event()
        event.add('summary', event_data['title'])
        
        # iCal events are typically all-day if no time is specified
        # We set it as an all-day event
        event.add('dtstart', event_data['start_date'].date())
        event.add('description', f"{event_data['description']}\n\nMore info: {event_data['url']}")
        event.add('location', 'The Gabba, Vulture St, Woolloongabba QLD 4102, Australia')
        event.add('url', event_data['url'])
        event.add('uid', f"{event_data['start_date'].strftime('%Y%m%d')}-{event_data['title'].replace(' ', '')}@thegabba.com.au")
        
        cal.add_component(event)

    try:
        with open(OUTPUT_FILE, 'wb') as f:
            f.write(cal.to_ical())
        print(f"Successfully wrote {len(events)} events to {OUTPUT_FILE}")
    except IOError as e:
        print(f"Error: Could not write to file {OUTPUT_FILE}. {e}")

if __name__ == "__main__":
    # --- A small warning before we start ---
    print("--- Gabba iCal Scraper ---")
    print("IMPORTANT: Web scraping can be fragile and may be against a")
    print("website's Terms of Service. Please use this script responsibly.")
    print("Check 'thegabba.com.au/robots.txt' for scraping policies.")
    print("This script is for personal, non-commercial use only.")
    print("---------------------------------")
    
    events = scrape_gabba_events()
    if events:
        create_ical_file(events)
    else:
        print("No events found or parsed, iCal file was not updated.")
    
    print("Script finished.")
