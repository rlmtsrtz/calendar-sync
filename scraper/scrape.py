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
    # Datum extrahieren (Format: DD.MM.YYYY)
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', date_str)
    if not match:
        return None

    # Zeit bereinigen (Format: HH:MM)
    time_match = re.search(r'(\d{2}:\d{2})', time_str)
    time_clean = time_match.group(1) if time_match else "12:00"

    full_str = f"{match.group(1)} {time_clean}"
    try:
        return datetime.strptime(full_str, "%d.%m.%Y %H:%M")
    except ValueError:
        return None

def scrape_team(team_url, team_id):
    # WUNSCH: Wir nutzen direkt die vom User bereitgestellte URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.fussball.de/'
    }

    print(f"DEBUG: Scrape Start für URL: {team_url}")

    try:
        # Wir laden die Seite. Falls es die Übersicht ist, versuchen wir auch den Spielplan-Tab zu finden.
        response = requests.get(team_url, headers=headers, timeout=20)

        if response.status_code != 200:
            print(f"DEBUG: Fehler beim Abrufen der URL ({response.status_code}).")
            return None

        # Checken ob wir auf die Startseite umgeleitet wurden
        if "willkommen-beim-amateurfussball" in response.url:
            print(f"DEBUG: Wurde zur Startseite umgeleitet. URL scheint ungültig.")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        # Suche nach den Match-Zeilen
        # Fussball.de nutzt 'row-match' in fast allen Tabellen (Übersicht und Spielplan)
        rows = soup.find_all('tr', class_='row-match')

        if not rows:
            print("DEBUG: Keine 'row-match' Zeilen gefunden. Suche nach alternativen Tabellen...")
            # Fallback: Suche nach allen Zeilen in Tabellen, die Teamnamen enthalten könnten
            rows = soup.select('.table-matchplan tr') or soup.select('.club-matchplan-table tr')

        print(f"DEBUG: {len(rows)} potenzielle Zeilen gefunden.")

        matches = []
        for row in rows:
            try:
                # Suche Zellen für Datum, Zeit, Heim, Gast
                date_cell = row.find('td', class_='column-date') or row.find('td', class_='column-date-short')
                time_cell = row.find('td', class_='column-time')
                home_cell = row.find('td', class_='column-team-home')
                away_cell = row.find('td', class_='column-team-away')

                if not (date_cell and time_cell and home_cell and away_cell):
                    continue

                home_name_div = home_cell.find('div', class_='club-name') or home_cell
                away_name_div = away_cell.find('div', class_='club-name') or away_cell

                home_name = home_name_div.text.strip()
                away_name = away_name_div.text.strip()

                dt = parse_date(date_cell.text.strip(), time_cell.text.strip())

                if dt:
                    matches.append({
                        'start': dt.isoformat(),
                        'summary': f"{home_name} - {away_name}",
                        'description': f"Heim: {home_name}\nGast: {away_name}\nQuelle: {team_url}",
                        'location': "Sportplatz"
                    })
            except Exception as e:
                continue

        print(f"DEBUG: {len(matches)} gültige Spiele extrahiert.")
        return matches
    except Exception as e:
        print(f"DEBUG: Kritischer Fehler beim Scrapen: {e}")
        return None

def create_calendar(name):
    cal = Calendar()
    cal.add('prodid', '-//Fussball.de Calendar//')
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
        event.add('uid', str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{m['summary']}_{m['start']}")) + "@tus-dornberg.de")
        event.add('dtstamp', datetime.now())
        cal.add_component(event)

def main():
    print("DEBUG: Scraper gestartet.")
    firebase_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not firebase_json:
        print("DEBUG: FIREBASE_SERVICE_ACCOUNT fehlt!")
        return

    try:
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"DEBUG: Firebase Fehler: {e}")
        return

    db = firestore.client()
    teams_ref = db.collection('teams')
    docs = list(teams_ref.stream())
    print(f"DEBUG: {len(docs)} Teams aus Firestore geladen.")

    os.makedirs('web/calendars', exist_ok=True)
    master_cal = create_calendar("TuS Dornberg Kombi")

    # Dummy Termin für Sync-Check
    dummy_date = (datetime.now() + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
    add_to_calendar(master_cal, [{
        'start': dummy_date.isoformat(),
        'summary': "DEBUG: Kalender aktiv!",
        'description': "Dieser Termin zeigt, dass die Synchronisation funktioniert.",
        'location': "Dornberg"
    }])

    all_matches_count = 0
    for doc in docs:
        team = doc.to_dict()
        team_id = team.get('id')
        team_url = team.get('url')
        team_name = team.get('name', 'Unbekannt')

        if not team_id: continue

        print(f"DEBUG: Verarbeite: {team_name}")
        matches = scrape_team(team_url, team_id)

        if matches:
            # Einzel-ICS
            ind_cal = create_calendar(f"Spielplan {team_name}")
            add_to_calendar(ind_cal, matches)
            with open(f'web/calendars/{team_id}.ics', 'wb') as f:
                f.write(ind_cal.to_ical())

            # Kombi-ICS
            add_to_calendar(master_cal, matches)
            all_matches_count += len(matches)

            # Update Firestore Vorschau
            doc.reference.update({'lastMatches': matches[:10]})
        else:
            doc.reference.update({'lastMatches': []})

    with open('web/calendars/all_teams.ics', 'wb') as f:
        f.write(master_cal.to_ical())
    print(f"DEBUG: Fertig. Total Spiele: {all_matches_count}")

if __name__ == "__main__":
    main()
