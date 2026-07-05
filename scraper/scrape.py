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
    if len(date_part.split('.')[-1]) == 2:
        parts = date_part.split('.')
        date_part = f"{parts[0]}.{parts[1]}.20{parts[2]}"

    full_str = f"{date_part} {time_clean}"
    try:
        return datetime.strptime(full_str, "%d.%m.%Y %H:%M")
    except ValueError:
        return None

def scrape_team(team_url, team_id, team_filter_name):
    # WUNSCH: Wir nutzen den Mannschaftsspielplan via AJAX Resource
    # Der User hat herausgefunden, dass dieser Link alle Spiele liefert:
    # https://www.fussball.de/ajax.team.matchplan/-/mode/PAGE/team-id/{team_id}

    ajax_resource_url = f"https://www.fussball.de/ajax.team.matchplan/-/mode/PAGE/team-id/{team_id}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': team_url
    }

    print(f"DEBUG: Scrape Start via AJAX Resource: {ajax_resource_url}")

    try:
        response = requests.get(ajax_resource_url, headers=headers, timeout=20)

        # Falls die AJAX Resource fehlschlägt, nutzen wir als Fallback die vom User bereitgestellte URL
        if response.status_code != 200:
            print(f"DEBUG: AJAX Resource fehlgeschlagen ({response.status_code}). Versuche Original-URL.")
            response = requests.get(team_url, headers=headers, timeout=20)

        if response.status_code != 200:
            print(f"DEBUG: Fehler beim Abrufen der Seite ({response.status_code}).")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        # Wir suchen alle Tabellen-Bodys
        tbodies = soup.find_all('tbody')
        if not tbodies:
            print("DEBUG: Kein <tbody> gefunden.")
            return None

        matches = []
        current_date_str = ""
        current_time_str = ""

        for tbody in tbodies:
            rows = tbody.find_all('tr')
            for row in rows:
                classes = row.get('class', [])

                # Datum extrahieren aus row-headline oder row-competition
                if 'row-competition' in classes or 'row-headline' in classes:
                    date_cell = row.find('td', class_='column-date')
                    if date_cell:
                        text = date_cell.get_text(strip=True)
                        if '|' in text:
                            # Wir prüfen ob ein Datum enthalten ist
                            parts = text.split('|')
                            date_candidate = parts[0].strip()
                            time_candidate = parts[1].strip()

                            if re.search(r'\d{2}\.\d{2}', date_candidate):
                                current_date_str = date_candidate

                            # Die Zeit nehmen wir immer wenn sie da steht
                            if re.search(r'\d{2}:\d{2}', time_candidate):
                                current_time_str = time_candidate
                        else:
                            # Nur Datum oder nur Zeit?
                            if re.search(r'\d{2}\.\d{2}', text):
                                current_date_str = text.strip()
                            if re.search(r'\d{2}:\d{2}', text):
                                current_time_str = text.strip()

                    # Mobile Headline Check
                    headline_text = row.get_text(strip=True)
                    if 'row-headline' in classes:
                        match = re.search(r'(\d{2}\.\d{2}\.\d{4}) - (\d{2}:\d{2})', headline_text)
                        if match:
                            current_date_str = match.group(1)
                            current_time_str = match.group(2)
                    continue

                # Spiel-Daten extrahieren (Vereine)
                club_cells = row.find_all('td', class_='column-club')
                if len(club_cells) >= 2 and current_date_str:
                    home_name_div = club_cells[0].find('div', class_='club-name')
                    away_name_div = club_cells[1].find('div', class_='club-name')

                    if home_name_div and away_name_div:
                        home_text = home_name_div.get_text(strip=True)
                        away_text = away_name_div.get_text(strip=True)

                        dt = parse_date(current_date_str, current_time_str)
                        if dt:
                            # WUNSCH: Heimspiel ist wahr, wenn "Dornberg" im Namen des ERSTEN Teams vorkommt.
                            is_home = "dornberg" in home_text.lower()

                            matches.append({
                                'start': dt.isoformat(),
                                'summary': f"{home_text} - {away_text}",
                                'description': f"Heim: {home_text}\nGast: {away_text}\nQuelle: {team_url}",
                                'location': "Sportplatz",
                                'isHome': is_home
                            })

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

def add_to_calendar(cal, matches, filter_type='all'):
    for m in matches:
        if filter_type == 'home' and not m['isHome']: continue
        if filter_type == 'away' and m['isHome']: continue

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

    # Master Kalender
    master_all = create_calendar("TuS Dornberg Kombi (Alle)")
    master_home = create_calendar("TuS Dornberg Kombi (Heim)")
    master_away = create_calendar("TuS Dornberg Kombi (Auswärts)")

    all_matches_count = 0
    for doc in docs:
        team = doc.to_dict()
        team_id = team.get('id')
        team_url = team.get('url')
        team_name = team.get('name', 'Unbekannt')
        if not team_id: continue

        print(f"DEBUG: Verarbeite: {team_name}")
        matches = scrape_team(team_url, team_id, team_name)

        if matches:
            for t in ['all', 'home', 'away']:
                suffix = "" if t == "all" else f"_{t}"
                cal_name = team_name + ("" if t == "all" else f" ({'Heim' if t == 'home' else 'Auswärts'})")
                ind_cal = create_calendar(f"Spielplan {cal_name}")
                add_to_calendar(ind_cal, matches, filter_type=t)
                with open(f'web/calendars/{team_id}{suffix}.ics', 'wb') as f:
                    f.write(ind_cal.to_ical())

            add_to_calendar(master_all, matches, 'all')
            add_to_calendar(master_home, matches, 'home')
            add_to_calendar(master_away, matches, 'away')

            all_matches_count += len(matches)
            doc.reference.update({'lastMatches': matches[:100]}) # Alle Spiele in die Vorschau
        else:
            doc.reference.update({'lastMatches': []})

    with open('web/calendars/all_teams.ics', 'wb') as f:
        f.write(master_all.to_ical())
    with open('web/calendars/all_teams_home.ics', 'wb') as f:
        f.write(master_home.to_ical())
    with open('web/calendars/all_teams_away.ics', 'wb') as f:
        f.write(master_away.to_ical())

    print(f"DEBUG: Fertig. Total Spiele: {all_matches_count}")

if __name__ == "__main__":
    main()
