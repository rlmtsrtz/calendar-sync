import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import json
import os
from datetime import datetime
import re

def parse_date(date_str, time_str):
    # Example date_str: "So, 10.09.2023"
    # Example time_str: "15:00"
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

    # The structure on fussball.de for matchplan rows
    # This might need adjustment based on the actual HTML
    table = soup.find('div', id='team-matchplan-table')
    if not table:
        # Fallback to general search if ID is different
        table = soup.find('table', class_='table-matchplan')

    if not table:
        print("Could not find matchplan table")
        return None

    rows = table.find_all('tr', class_='row-match')
    for row in rows:
        try:
            date_cell = row.find('td', class_='column-date')
            time_cell = row.find('td', class_='column-time')
            team_home = row.find('td', class_='column-team-home').find('div', class_='club-name').text.strip()
            team_away = row.find('td', class_='column-team-away').find('div', class_='club-name').text.strip()

            # Location often in a tooltip or separate column
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
        # Assume 105 minutes (90 + halftime + buffer)
        from datetime import timedelta
        event.add('dtend', m['start'] + timedelta(minutes=105))
        event.add('description', m['description'])
        event.add('location', m['location'])
        cal.add_component(event)

    os.makedirs('web/calendars', exist_ok=True)
    with open(f'web/calendars/{team_id}.ics', 'wb') as f:
        f.write(cal.to_ical())

def main():
    with open('scraper/teams.json', 'r', encoding='utf-8') as f:
        teams = json.load(f)

    for team in teams:
        print(f"Scraping {team['name']} ({team['id']})...")
        matches = scrape_team(team['id'])
        if matches:
            generate_ics(team['id'], team['name'], matches)
            print(f"Generated calendar for {team['name']}")
        else:
            print(f"No matches found for {team['name']}")

if __name__ == "__main__":
    main()
