import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import json
import os
from datetime import datetime, timedelta
import re
import firebase_admin
from firebase_admin import credentials, firestore

def parse_date(date_str, time_str):
    # Example date_str: "So, 10.09.2023"
    # Example time_str: "15:00"
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', date_str)
    if not match:
        return None

    # Check if time is "Absetz." or similar
    if not re.match(r'^\d{2}:\d{2}$', time_str):
        time_str = "00:00" # Fallback to midnight if no time is set

    full_str = f"{match.group(1)} {time_str}"
    try:
        return datetime.strptime(full_str, "%d.%m.%Y %H:%M")
    except ValueError:
        return None

def scrape_team(team_id):
    url = f"https://www.fussball.de/mannschaft/-/-/team-id/{team_id}#!/section/team-matchplan"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch {url} - Status: {response.status_code}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    matches = []

    # Fussball.de often uses 'team-matchplan-table' or a specific table class
    table = soup.find('div', id='team-matchplan-table')
    if not table:
        table = soup.find('table', class_='table-matchplan')

    if not table:
        # Debugging: Print a bit of the soup to see what we got
        print(f"Could not find matchplan table for {team_id}. Page title: {soup.title.string if soup.title else 'No Title'}")
        return None

    rows = table.find_all('tr', class_='row-match')
    print(f"Found {len(rows)} potential match rows for {team_id}")

    for row in rows:
        try:
            # Skip hidden rows or non-match rows
            if 'display-none' in row.get('class', []):
                continue

            date_cell = row.find('td', class_='column-date')
            time_cell = row.find('td', class_='column-time')

            home_div = row.find('td', class_='column-team-home').find('div', class_='club-name')
            away_div = row.find('td', class_='column-team-away').find('div', class_='club-name')

            if not home_div or not away_div:
                continue

            team_home = home_div.text.strip()
            team_away = away_div.text.strip()

            location = "Siehe fussball.de"
            # Try to find a more specific location if available (sometimes in data attributes or separate cells)

            dt = parse_date(date_cell.text.strip(), time_cell.text.strip())
            if dt:
                matches.append({
                    'start': dt,
                    'summary': f"{team_home} - {team_away}",
                    'description': f"Heim: {team_home}\nGast: {team_away}\nLink: {url}",
                    'location': location
                })
        except Exception as e:
            print(f"Error parsing row for {team_id}: {e}")

    return matches

def create_calendar(name):
    cal = Calendar()
    cal.add('prodid', '-//Fussball.de Calendar Generator//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', name)
    cal.add('x-wr-timezone', 'Europe/Berlin')
    return cal

def add_to_calendar(cal, matches):
    for m in matches:
        event = Event()
        event.add('summary', m['summary'])
        event.add('dtstart', m['start'])
        event.add('dtend', m['start'] + timedelta(minutes=105))
        event.add('description', m['description'])
        event.add('location', m['location'])
        # Add a unique ID to help Google Calendar identify changes
        import uuid
        event.add('uid', str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{m['summary']}_{m['start']}")))
        cal.add_component(event)

def main():
    firebase_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if firebase_json:
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    else:
        try:
            cred = credentials.Certificate('service-account.json')
            firebase_admin.initialize_app(cred)
        except:
            print("No Firebase credentials found.")
            return

    db = firestore.client()
    teams_ref = db.collection('teams')
    docs = list(teams_ref.stream())

    os.makedirs('web/calendars', exist_ok=True)

    # Master calendar for all teams
    master_cal = create_calendar("Alle Mannschaften - TuS Dornberg")
    all_matches_count = 0

    for doc in docs:
        team = doc.to_dict()
        team_id = team.get('id')
        team_name = team.get('name', 'Unbekannt')

        if not team_id:
            continue

        print(f"Scraping {team_name} ({team_id})...")
        matches = scrape_team(team_id)

        if matches:
            # Individual calendar
            ind_cal = create_calendar(f"Spielplan {team_name}")
            add_to_calendar(ind_cal, matches)
            with open(f'web/calendars/{team_id}.ics', 'wb') as f:
                f.write(ind_cal.to_ical())

            # Add to master calendar
            add_to_calendar(master_cal, matches)
            all_matches_count += len(matches)
            print(f"Success: {len(matches)} matches added for {team_name}")
        else:
            print(f"No matches found for {team_name}")

    # Save master calendar
    with open('web/calendars/all_teams.ics', 'wb') as f:
        f.write(master_cal.to_ical())
    print(f"Master calendar generated with {all_matches_count} total matches.")

if __name__ == "__main__":
    main()
