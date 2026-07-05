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
    # Datum extrahieren (Format: DD.MM.YYYY oder DD.MM.YY)
    match = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', date_str)
    if not match:
        return None

    # Zeit bereinigen (Format: HH:MM)
    time_match = re.search(r'(\d{2}:\d{2})', time_str)
    time_clean = time_match.group(1) if time_match else "12:00"

    date_part = match.group(1)
    # Falls das Jahr nur zweistellig ist, ergänzen wir 20
    if len(date_part.split('.')[-1]) == 2:
        parts = date_part.split('.')
        date_part = f"{parts[0]}.{parts[1]}.20{parts[2]}"

    full_str = f"{date_part} {time_clean}"
    try:
        return datetime.strptime(full_str, "%d.%m.%Y %H:%M")
    except ValueError:
        return None

def scrape_team(team_url, team_id):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.fussball.de/'
    }

    print(f"DEBUG: Scrape Start für URL: {team_url}")

    try:
        response = requests.get(team_url, headers=headers, timeout=20)
        if response.status_code != 200:
            print(f"DEBUG: Fehler beim Abrufen der URL ({response.status_code}).")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        # Wir suchen alle Zeilen im Table-Body
        tbody = soup.find('tbody')
        if not tbody:
            print("DEBUG: Kein <tbody> gefunden.")
            return None

        rows = tbody.find_all('tr')
        print(f"DEBUG: {len(rows)} Zeilen im <tbody> gefunden.")

        matches = []
        current_date_str = ""
        current_time_str = ""

        for row in rows:
            classes = row.get('class', [])

            # Fall 1: Zeile mit Datum und Wettbewerb (row-competition oder row-headline)
            if 'row-competition' in classes or 'row-headline' in classes:
                date_cell = row.find('td', class_='column-date')
                if date_cell:
                    # Format oft: "So, 12.07.26 | 12:00"
                    text = date_cell.get_text(strip=True)
                    if '|' in text:
                        current_date_str, current_time_str = text.split('|')
                    else:
                        current_date_str = text

                # Falls row-headline (mobile): "Sonntag, 12.07.2026 - 12:00 Uhr | ..."
                headline_text = row.get_text(strip=True)
                if 'row-headline' in classes and not current_date_str:
                    match = re.search(r'(\d{2}\.\d{2}\.\d{4}) - (\d{2}:\d{2})', headline_text)
                    if match:
                        current_date_str = match.group(1)
                        current_time_str = match.group(2)
                continue

            # Fall 2: Zeile mit den Vereinen (Keine spezielle Klasse für Wettbewerb/Headline)
            # Wir prüfen ob es zwei Spalten mit 'column-club' gibt
            club_cells = row.find_all('td', class_='column-club')
            if len(club_cells) >= 2 and current_date_str:
                home_name = club_cells[0].find('div', class_='club-name')
                away_name = club_cells[1].find('div', class_='club-name')

                if home_name and away_name:
                    home_text = home_name.get_text(strip=True)
                    away_text = away_name.get_text(strip=True)

                    dt = parse_date(current_date_str.strip(), current_time_str.strip())
                    if dt:
                        matches.append({
                            'start': dt.isoformat(),
                            'summary': f"{home_text} - {away_text}",
                            'description': f"Heim: {home_text}\nGast: {away_text}\nQuelle: {team_url}",
                            'location': "Sportplatz"
                        })
                        # Wir setzen die Zeit zurück, damit sie nicht für die nächste Zeile (falls vorhanden) doppelt genutzt wird,
                        # es sei denn es kommt eine neue Headline
                        # current_date_str = ""

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
