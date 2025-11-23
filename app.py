"""
Streamlit Contact Scraper
- Drop-in single-file Streamlit app.
- Upload an Excel file (first column should be company names).
- App searches for official website, scrapes emails and phone numbers from the site, and returns an Excel output.

Design choices to reduce blocking and be practical:
- Uses `googlesearch` for finding candidate URLs (same as your Colab). If you prefer a paid API (SerpAPI/Bing) you can swap it easily.
- Randomized User-Agent rotation and configurable delays between requests.
- Requests session with retry/backoff for resilience.
- Option to provide proxy list (HTTP[s] proxies) if you have them.

Usage:
1. `pip install streamlit googlesearch-python beautifulsoup4 requests pandas openpyxl` 
2. `streamlit run streamlit_contact_scraper.py`

Keep it simple and sturdy.
"""

import streamlit as st
import pandas as pd
import time
import re
import requests
import random
from bs4 import BeautifulSoup
from googlesearch import search
from io import BytesIO
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Helper utilities ---
USER_AGENTS = [
    # a short but varied list
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
]

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(r'\+?\d[\d\s().-]{6,}\d')


def make_session(timeout=10, max_retries=3, backoff_factor=0.5, proxies=None):
    s = requests.Session()
    retries = Retry(total=max_retries, backoff_factor=backoff_factor,
                    status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET", "POST"])
    s.mount('http://', HTTPAdapter(max_retries=retries))
    s.mount('https://', HTTPAdapter(max_retries=retries))
    s.request_timeout = timeout
    if proxies:
        s.proxies.update(proxies)
    return s


def find_website(company, num_results=3, pause=2):
    query = f"{company} official site"
    try:
        # use googlesearch; `pause` controls delay between Google queries
        url = next(search(query, num=num_results, stop=1, pause=pause), None)
        return url
    except Exception:
        return None


def extract_contacts_from_url(session, url):
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        r = session.get(url, headers=headers, timeout=session.request_timeout)
        text = BeautifulSoup(r.text, 'html.parser').get_text(separator=' ')
        emails = set(EMAIL_REGEX.findall(text))
        phones = set(PHONE_REGEX.findall(text))
        return ', '.join(sorted(emails)), ', '.join(sorted(phones))
    except Exception:
        return '', ''


# --- Streamlit UI ---
st.set_page_config(page_title='Company Contact Scraper', layout='wide')
st.title('📇 Company Contact Scraper — Streamlined & resilient')

st.markdown('Upload an Excel file where the **first column** contains company names. The app will search for the company site, gather emails and phone numbers, and produce an Excel for download.')

uploaded_file = st.file_uploader('Upload Excel (xlsx)', type=['xlsx'])

col1, col2, col3 = st.columns([2,1,1])
with col1:
    delay_min = st.number_input('Min delay between company searches (seconds)', min_value=1.0, max_value=30.0, value=2.0, step=0.5)
with col2:
    delay_max = st.number_input('Max delay between company searches (seconds)', min_value=1.0, max_value=30.0, value=5.0, step=0.5)
with col3:
    pause_google = st.slider('Google pause param (internal)', 1, 5, 2)

use_proxies = st.checkbox('Use proxies (optional)', value=False)
proxy_text = ''
if use_proxies:
    proxy_text = st.text_area('Paste proxies (one per line) in format http://user:pass@host:port or http://host:port', height=120)

ua_rotate = st.checkbox('Rotate User-Agents (recommended)', value=True)

start_button = st.button('▶ Start Extraction')
stop_button = st.button('🛑 Cancel')

# session flags
if 'stop_flag' not in st.session_state:
    st.session_state.stop_flag = False
if 'running' not in st.session_state:
    st.session_state.running = False

if stop_button:
    st.session_state.stop_flag = True
    st.session_state.running = False
    st.success('⚠️ Cancel requested — stopping after current company.')


if start_button and uploaded_file and not st.session_state.running:
    st.session_state.stop_flag = False
    st.session_state.running = True

    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f'Error reading Excel file: {e}')
        st.session_state.running = False
    else:
        company_column = df.columns[0]
        companies = df[company_column].astype(str).fillna('').tolist()
        df['Website'] = ''
        df['Emails'] = ''
        df['Phones'] = ''

        # prepare proxies if provided
        proxies = None
        proxy_list = []
        if use_proxies and proxy_text.strip():
            proxy_lines = [line.strip() for line in proxy_text.splitlines() if line.strip()]
            for p in proxy_lines:
                proxy_list.append({'http': p, 'https': p})

        session = make_session(timeout=15, max_retries=3, backoff_factor=1, proxies=None)

        progress = st.progress(0)
        status_area = st.empty()

        for i, company in enumerate(companies):
            if st.session_state.stop_flag:
                status_area.info('🛑 Cancelled by user.')
                break

            status_area.info(f'🔍 [{i+1}/{len(companies)}] Searching: {company}')

            # optional rotate proxies per request (if user supplied proxies)
            if proxy_list:
                session.proxies.update(random.choice(proxy_list))

            # pick UA
            if ua_rotate:
                session_headers = {'User-Agent': random.choice(USER_AGENTS)}
            else:
                session_headers = {'User-Agent': USER_AGENTS[0]}

            # find website
            try:
                website = find_website(company, num_results=3, pause=pause_google)
            except Exception:
                website = None

            if website:
                df.at[i, 'Website'] = website
                emails, phones = extract_contacts_from_url(session, website)
                df.at[i, 'Emails'] = emails
                df.at[i, 'Phones'] = phones
            else:
                df.at[i, 'Website'] = 'Not Found'

            progress.progress((i+1)/len(companies))

            # randomized sleep between min and max
            sleep_time = random.uniform(delay_min, delay_max)
            time.sleep(sleep_time)

        st.session_state.running = False

        # show and download result
        st.success('✅ Extraction finished (or stopped). Review below and download.')
        st.dataframe(df)

        towrite = BytesIO()
        df.to_excel(towrite, index=False, engine='openpyxl')
        towrite.seek(0)

        st.download_button('⬇️ Download Excel', towrite, file_name='Company_Contacts.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

elif start_button and not uploaded_file:
    st.warning('Please upload an Excel (.xlsx) file first.')

# Helpful tips
st.markdown('---')
st.markdown('**Tips to reduce blocking**: use reasonable delays (2–7s), rotate user agents, and (if available) use paid search APIs or proxies. Avoid making repeated identical requests. If you plan to run at scale, consider SerpAPI/Bing with an API key.')

st.caption('This is a practical, drop-in app — keep it honest and respectful to search providers.')
