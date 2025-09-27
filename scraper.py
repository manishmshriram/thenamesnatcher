import requests
import pandas as pd
import time, random
from bs4 import BeautifulSoup
import re

USER_AGENTS = [
    # Add multiple modern desktop/mobile user-agents for rotation
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64)...', # (Add more for anti-block)
]

def google_search(company, country=None):
    base = "https://www.google.com/search?q="
    query = company if not country else f"{company} {country} official website"
    headers = {
        "User-Agent": random.choice(USER_AGENTS)
    }
    # Add random wait before every request
    time.sleep(random.uniform(2,6))
    resp = requests.get(base + requests.utils.quote(query), headers=headers)
    soup = BeautifulSoup(resp.text, 'html.parser')
    link = ""
    for cite in soup.select('a'):
        href = cite.attrs.get('href', '')
        if href.startswith('/url?q=') and 'google.com' not in href and 'webcache' not in href:
            link = href.split('/url?q=')[1].split('&')[0]
            break
    return link

def extract_contact_from_page(url):
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        page = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(page.text, 'html.parser')
        emails = set(re.findall(r"[a-zA-Z0-9.\-+_]+@[a-zA-Z0-9\-.]+\.[a-zA-Z]+", page.text))
        phones = set(re.findall(r"\+?[0-9][0-9()\-\s]{7,}[0-9]", page.text))
        email = ', '.join(emails) if emails else None
        phone = ', '.join(phones) if phones else None
        return email, phone
    except Exception as e:
        return None, None

def extract_contacts_bulk(df, batch_size=10, delay=4):
    results = []
    for idx, row in df.iterrows():
        company = row['Company']
        country = row['Country'] if 'Country' in row else None
        website = google_search(company, country)
        email, phone = (None, None)
        if website:
            email, phone = extract_contact_from_page(website)
        results.append({
            'Company': company,
            'Country': country,
            'Website': website,
            'Email': email,
            'Phone': phone
        })
        if (idx+1) % batch_size == 0:
            time.sleep(delay*batch_size)
    return pd.DataFrame(results)
