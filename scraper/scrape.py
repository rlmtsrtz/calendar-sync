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
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', date_str)
    if not match:
        return None

    full_str = f"{match.group(1)} {time_str}"
    try:
        return datetime.strptime(full_str, "%d.%m.%Y %H:%M")
    except ValueError:
        return None

def scrape_team(team_id):
    url = f"https://www.fussball.de/mannschaft/-/-/team-id/{team_id}#!/section/team-matchplan"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch {url}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    matches = []

    table = soup.find('div', id='team-matchplan-table')
    if not table:
        table = soup.find('table', class_='table-matchplan')

    if not table:
        print(f"Could not find matchplan table for {team_id}")
        return None

    rows = table.find_all('tr', class_='row-match')
    for row in rows:
        try:
            date_cell = row.find('td', class_='column-date')
            time_cell = row.find('td', class_='column-time')

            home_div = row.find('td', class_='column-team-home').find('div', class_='club-name')
            away_div = row.find('td', class_='column-team-away').find('div', class_='club-name')

            if not home_div or not away_div:
                continue

            team_home = home_div.text.strip()
            team_away = away_div.text.strip()

            location = "Siehe fussball.de"

            dt = parse_date(date_cell.text.strip(), time_cell.text.strip())
            if dt:
                matches.append({
                    'start': dt,
                    'summary': f"{team_home} vs. {team_away}",
                    'description': f"Heim: {team_home}\nGast: {team_away}",
                    'location': location
                })
        except Exception as e:
            print(f"Error parsing row: {e}")

    return matches

def generate_ics(team_id, team_name, matches):
    cal = Calendar()
    cal.add('prodid', '-//Fussball.de Calendar Generator//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', f"Spielplan {team_name}")

    for m in matches:
        event = Event()
        event.add('summary', m['summary'])
        event.add('dtstart', m['start'])
        event.add('dtend', m['start'] + timedelta(minutes=105))
        event.add('description', m['description'])
        event.add('location', m['location'])
        cal.add_component(event)

    os.makedirs('web/calendars', exist_ok=True)
    with open(f'web/calendars/{team_id}.ics', 'wb') as f:
        f.write(cal.to_ical())

def main():
    # Initialize Firebase
    # On local, you'd use a service account json file.
    # On GitHub Actions, we'll pass the JSON via environment variable.
    firebase_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if firebase_json:
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    else:
        # Fallback for local testing if you have a file
        try:
            cred = credentials.Certificate('service-account.json')
            firebase_admin.initialize_app(cred)
        except:
            print("No Firebase credentials found. Set FIREBASE_SERVICE_ACCOUNT env var.")
            return

    db = firestore.client()
    teams_ref = db.collection('teams')
    docs = teams_ref.stream()

    for doc in docs:
        team = doc.to_dict()
        team_id = team.get('id')
        team_name = team.get('name', 'Unbekannt')

        if not team_id:
            continue

        print(f"Scraping {team_name} ({team_id})...")
        matches = scrape_team(team_id)
        if matches:
            generate_ics(team_id, team_name, matches)
            print(f"Generated calendar for {team_name}")
        else:
            print(f"No matches found for {team_name}")

if __name__ == "__main__":
    main()
