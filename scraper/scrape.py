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
import time

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

def get_game_location(detail_url):
    """Ruft die Detailseite eines Spiels auf und extrahiert den Spielort."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        # Kurze Pause um fussball.de nicht zu überlasten
        time.sleep(0.3)
        response = requests.get(detail_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # Die Adresse steht oft in einem Element mit icon-location
            full_text = soup.get_text()

            # Wir prüfen auf deine spezifische Heim-Adresse
            # Kirchdornberger Str. 46, 33619 Bielefeld
            is_home = False
            if "Kirchdornberger Str" in full_text and "33619" in full_text:
                is_home = True
            elif "BIPA-Sportarena" in full_text:
                is_home = True

            # Location Text extrahieren für den Kalender-Eintrag
            location_text = "Unbekannter Ort"
            loc_icon = soup.find('span', class_='icon-location')
            if loc_icon:
                # Text im Elternelement ohne das Wort "Anfahrt"
                location_text = loc_icon.parent.get_text(strip=True).replace('Anfahrt', '').strip()

            return location_text, is_home
    except Exception as e:
        print(f"DEBUG: Fehler beim Location-Check: {e}")

    return "Sportplatz", False

def scrape_team(team_url, team_id, team_filter_name):
    # AJAX-URL für den kompletten Spielplan
    ajax_resource_url = f"https://www.fussball.de/ajax.team.matchplan/-/mode/PAGE/team-id/{team_id}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'de-DE,de;q=0.9',
        'Referer': team_url
    }

    print(f"DEBUG: Scrape Start für {team_filter_name} via AJAX")

    try:
        response = requests.get(ajax_resource_url, headers=headers, timeout=20)
        if response.status_code != 200:
            print(f"DEBUG: AJAX Fehler {response.status_code}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        tbodies = soup.find_all('tbody')
        if not tbodies:
            return None

        matches = []
        current_date_str = ""
        current_time_str = ""

        for tbody in tbodies:
            rows = tbody.find_all('tr')
            for row in rows:
                classes = row.get('class', [])

                # Datum merken (für Spiele ohne eigenes Datum in der Zeile)
                if 'row-competition' in classes or 'row-headline' in classes:
                    date_cell = row.find('td', class_='column-date')
                    if date_cell:
                        text = date_cell.get_text(strip=True)
                        if '|' in text:
                            parts = text.split('|')
                            if re.search(r'\d{2}\.\d{2}', parts[0]):
                                current_date_str = parts[0].strip()
                            current_time_str = parts[1].strip()
                        elif re.search(r'\d{2}\.\d{2}', text):
                            current_date_str = text.strip()

                    # Mobile Headline Fallback
                    if 'row-headline' in classes:
                        h_text = row.get_text(strip=True)
                        match = re.search(r'(\d{2}\.\d{2}\.\d{4}) - (\d{2}:\d{2})', h_text)
                        if match:
                            current_date_str = match.group(1)
                            current_time_str = match.group(2)
                    continue

                # Eigentliche Spiel-Zeile
                club_cells = row.find_all('td', class_='column-club')
                detail_cell = row.find('td', class_='column-detail')

                if len(club_cells) >= 2 and current_date_str:
                    home_name = club_cells[0].get_text(strip=True)
                    away_name = club_cells[1].get_text(strip=True)

                    # Link zum Spiel für den Location-Check
                    detail_link = None
                    if detail_cell and detail_cell.find('a'):
                        detail_link = detail_cell.find('a')['href']

                    # HEIM-LOGIK: Wir rufen die Detailseite auf und prüfen den Ort
                    is_real_home = False
                    location_name = "Sportplatz"

                    if detail_link:
                        print(f"DEBUG: Prüfe Ort für: {home_name} vs. {away_name}")
                        location_name, is_real_home = get_game_location(detail_link)

                    dt = parse_date(current_date_str, current_time_str)
                    if dt:
                        matches.append({
                            'start': dt.isoformat(),
                            'summary': f"{home_name} - {away_name}",
                            'description': f"Heim: {home_name}\nGast: {away_name}\nOrt: {location_name}\nLink: {detail_link}",
                            'location': location_name,
                            'isHome': is_real_home
                        })

        print(f"DEBUG: {len(matches)} Spiele erfolgreich mit Location-Check verarbeitet.")
        return matches
    except Exception as e:
        print(f"DEBUG: Kritischer Fehler: {e}")
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
    print("DEBUG: Scraper gestartet (Location-Logic active)")
    firebase_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not firebase_json:
        print("DEBUG: Kein Firebase Secret gefunden!")
        return

    try:
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"DEBUG: Firebase Init Fehler: {e}")
        return

    db = firestore.client()
    teams_ref = db.collection('teams')
    docs = list(teams_ref.stream())

    os.makedirs('web/calendars', exist_ok=True)

    # Master Kalender
    master_all = create_calendar("TuS Dornberg Kombi (Alle)")
    master_home = create_calendar("TuS Dornberg Kombi (Heim)")
    master_away = create_calendar("TuS Dornberg Kombi (Auswärts)")

    for doc in docs:
        team = doc.to_dict()
        team_id = team.get('id')
        team_url = team.get('url')
        team_name = team.get('name', 'Unbekannt')
        if not team_id: continue

        print(f"DEBUG: Verarbeite Team: {team_name}")
        matches = scrape_team(team_url, team_id, team_name)

        if matches:
            # Einzel-ICS generieren
            for t in ['all', 'home', 'away']:
                suffix = "" if t == "all" else f"_{t}"
                cal_name = f"{team_name} ({t})"
                ind_cal = create_calendar(cal_name)
                add_to_calendar(ind_cal, matches, filter_type=t)
                with open(f'web/calendars/{team_id}{suffix}.ics', 'wb') as f:
                    f.write(ind_cal.to_ical())

            # In Master-Kalender einfügen
            add_to_calendar(master_all, matches, 'all')
            add_to_calendar(master_home, matches, 'home')
            add_to_calendar(master_away, matches, 'away')

            # Firestore Vorschau aktualisieren
            doc.reference.update({'lastMatches': matches[:100]})
        else:
            doc.reference.update({'lastMatches': []})

    # Master speichern
    with open('web/calendars/all_teams.ics', 'wb') as f:
        f.write(master_all.to_ical())
    with open('web/calendars/all_teams_home.ics', 'wb') as f:
        f.write(master_home.to_ical())
    with open('web/calendars/all_teams_away.ics', 'wb') as f:
        f.write(master_away.to_ical())

    print(f"DEBUG: Scraper erfolgreich beendet.")

if __name__ == "__main__":
    main()
