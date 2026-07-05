import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import json
import os
from datetime import datetime, timedelta
import re
import firebase_admin
from firebase_admin import credentials, firestore
import uuid

def parse_date(date_str, time_str):
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', date_str)
    if not match:
        return None

    if not re.match(r'^\d{2}:\d{2}$', time_str):
        time_str = "00:00"

    full_str = f"{match.group(1)} {time_str}"
    try:
        return datetime.strptime(full_str, "%d.%m.%Y %H:%M")
    except ValueError:
        return None

def scrape_team(team_id):
    url = f"https://www.fussball.de/mannschaft/-/-/team-id/{team_id}#!/section/team-matchplan"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        matches = []
        table = soup.find('div', id='team-matchplan-table') or soup.find('table', class_='table-matchplan')

        if not table:
            return None

        rows = table.find_all('tr', class_='row-match')
        for row in rows:
            if 'display-none' in row.get('class', []):
                continue

            date_cell = row.find('td', class_='column-date')
            time_cell = row.find('td', class_='column-time')
            home_div = row.find('td', class_='column-team-home').find('div', class_='club-name')
            away_div = row.find('td', class_='column-team-away').find('div', class_='club-name')

            if home_div and away_div:
                team_home = home_div.text.strip()
                team_away = away_div.text.strip()
                dt = parse_date(date_cell.text.strip(), time_cell.text.strip())
                if dt:
                    matches.append({
                        'start': dt.isoformat(),
                        'summary': f"{team_home} - {team_away}",
                        'description': f"Heim: {team_home}\nGast: {team_away}",
                        'location': "Sportplatz"
                    })
        return matches
    except Exception as e:
        print(f"Scrape error for {team_id}: {e}")
        return None

def create_calendar(name):
    cal = Calendar()
    cal.add('prodid', '-//Fussball.de Calendar Generator//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', name)
    cal.add('x-wr-timezone', 'Europe/Berlin')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    return cal

def add_to_calendar(cal, matches):
    for m in matches:
        event = Event()
        event.add('summary', m['summary'])
        dt_start = datetime.fromisoformat(m['start'])
        event.add('dtstart', dt_start)
        event.add('dtend', dt_start + timedelta(minutes=105))
        event.add('description', m['description'])
        event.add('location', m['location'])
        event.add('uid', str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{m['summary']}_{m['start']}")) + "@calendar.sync")
        event.add('dtstamp', datetime.now())
        cal.add_component(event)

def main():
    firebase_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if firebase_json:
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    else:
        print("No Firebase credentials found.")
        return

    db = firestore.client()
    teams_ref = db.collection('teams')
    docs = list(teams_ref.stream())

    os.makedirs('web/calendars', exist_ok=True)
    master_cal = create_calendar("TuS Dornberg Kombi")

    # 1. Add Dummy Event to Master for Testing
    dummy_matches = [{
        'start': (datetime.now() + timedelta(days=1, hours=10)).isoformat(),
        'summary': "TEST: Training Dornberg",
        'description': "Dies ist ein Dummy-Termin zur Prüfung der Synchronisation.",
        'location': "Kunstrasenplatz"
    }]
    add_to_calendar(master_cal, dummy_matches)

    for doc in docs:
        team = doc.to_dict()
        team_id = team.get('id')
        team_name = team.get('name', 'Unbekannt')
        if not team_id: continue

        matches = scrape_team(team_id)
        if matches:
            # Individual ICS
            ind_cal = create_calendar(f"Spielplan {team_name}")
            add_to_calendar(ind_cal, matches)
            with open(f'web/calendars/{team_id}.ics', 'wb') as f:
                f.write(ind_cal.to_ical())

            # Master ICS
            add_to_calendar(master_cal, matches)

            # Update Firestore with match preview
            doc.reference.update({'lastMatches': matches[:5]}) # Store first 5 matches for UI

    with open('web/calendars/all_teams.ics', 'wb') as f:
        f.write(master_cal.to_ical())

if __name__ == "__main__":
    main()
