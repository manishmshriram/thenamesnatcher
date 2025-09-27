import streamlit as st
import pandas as pd
import requests
import random
import time
from bs4 import BeautifulSoup
import re

# -- SETTINGS --
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:118.0) Gecko/20100101 Firefox/118.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 11_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Linux; Android 10; SM-A505F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36',
    # Add more if possible!
]

GOOGLE_BASE = "https://www.google.com/search?q="

def validate_input(df):
    """Ensure the required columns exist."""
    needed = ["Company"]
    for col in needed:
        if col not in df.columns:
            return False, f"Missing required column: '{col}'"
    return True, ""

def google_search(company, country=None, delay=4):
    """Get top organic website link from Google search."""
    query = company
    if country:
        query += f" {country} official website"
    url = GOOGLE_BASE + requests.utils.quote(query)
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    time.sleep(random.uniform(delay, delay + 2))
    try:
        resp = requests.get(url, headers=headers, timeout=9)
        soup = BeautifulSoup(resp.text, 'html.parser')
        link = ""
        # Find the first "organic result" anchor
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith("/url?q=") and "google.com" not in href:
                link = href.split("/url?q=")[1].split("&")[0]
                if link.startswith("http"):
                    return link
        return ""
    except Exception as ex:
        return ""

def extract_contact_from_page(url):
    """Extract first visible email and phone from the site (homepage or contact page)."""
    def fetch(url):
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            return resp.text
        except:
            return ""
    text = fetch(url)
    soup = BeautifulSoup(text, 'html.parser')
    # Email extract
    mails = set(re.findall(r"[a-zA-Z0-9\.\-+_]+@[a-zA-Z0-9\.\-+_]+\.[a-zA-Z]+", text))
    email = ", ".join(list(mails)) if mails else ""
    # Phone extract
    phones = set(re.findall(r"\+?\d[\d\s\-\(\)]{7,}\d", text))
    phone = ", ".join(list(phones)) if phones else ""
    # Try to crawl "Contact" page as well
    contact_link = ""
    for a in soup.find_all('a', href=True):
        if 'contact' in a['href'].lower() and a['href'].startswith('http'):
            contact_link = a['href']
            break
    if contact_link:
        text2 = fetch(contact_link)
        mails2 = set(re.findall(r"[a-zA-Z0-9\.\-+_]+@[a-zA-Z0-9\.\-+_]+\.[a-zA-Z]+", text2))
        phones2 = set(re.findall(r"\+?\d[\d\s\-\(\)]{7,}\d", text2))
        if mails2:
            email += (", " if email else "") + ", ".join(list(mails2))
        if phones2:
            phone += (", " if phone else "") + ", ".join(list(phones2))
    return email, phone

def process_leads(df, batch_size=5, delay=4):
    results = []
    n = len(df)
    for idx, row in df.iterrows():
        company = str(row['Company'])
        country = row['Country'] if 'Country' in row else ""
        # Progress
        st.info(f'Processing [{idx+1}/{n}]: {company} {country}')
        website = google_search(company, country, delay=delay)
        if not website:
            results.append({
                'Company': company,
                'Country': country,
                'Website': 'Not Found',
                'Email': '',
                'Phone': '',
                'Status': 'No Website Found'
            })
            continue
        email, phone = extract_contact_from_page(website)
        status = 'OK' if website else "No Website Found"
        results.append({
            'Company': company,
            'Country': country,
            'Website': website,
            'Email': email,
            'Phone': phone,
            'Status': status
        })
        if (idx+1) % batch_size == 0:
            time.sleep(random.uniform(delay+1, delay+3))
    return pd.DataFrame(results)

# --- STREAMLIT APP LOGIC ---
st.set_page_config(page_title="Lead Extractor | Free", layout="wide")
st.title("Company Website, Email and Contact Finder")

uploaded_file = st.file_uploader("Upload your company CSV/Excel file (with 'Company' column and optional 'Country')", type=['csv', 'xlsx'])

batch_size = st.slider("Batch size (fewer = safer against blocks)", 1, 10, 3)
delay = st.slider("Delay (seconds) between requests", 2, 10, 4)

if uploaded_file:
    if uploaded_file.name.endswith("csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    valid, msg = validate_input(df)
    if not valid:
        st.error(msg)
        st.stop()
    st.write(f"Preview of uploaded data ({len(df)} rows):")
    st.dataframe(df.head())

    if st.button("Start Extraction"):
        st.info("Extraction started. Please wait and do not refresh…")
        out_df = process_leads(df, batch_size=batch_size, delay=delay)
        st.success("Extraction complete 🎉 - Download your results below.")
        st.dataframe(out_df)
        st.download_button("Download Results as CSV", out_df.to_csv(index=False), "leads_results.csv")
else:
    st.markdown("""
    **Instructions:**
    - Prepare a CSV or Excel file with a column 'Company' with company names, and if possible, a 'Country' column.
    - Upload and start extraction.
    - Download clean CSV with all results and detailed status for each row.
    """)

