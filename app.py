"""
Streamlit Contact Scraper (Colab-style, accurate)

What this file does
- Replace googlesearch (which often triggers "line 7" import errors) with duckduckgo_search.
- Accepts a single company name or a bulk CSV/XLSX upload (one column with company names).
- For each company it searches top results, visits candidate pages (contact/about/home), extracts emails and phone numbers (also mailto: and tel: links), and collects them into a DataFrame.
- Lets you download the final results as an Excel (.xlsx) or CSV.

Install (one-liner):
    pip install streamlit pandas requests beautifulsoup4 duckduckgo_search openpyxl

Run:
    streamlit run streamlit_contact_scraper_app.py

Notes / tips:
- This app deliberately leans toward the "Colab slow-but-accurate" approach: you can configure number of search results per company and delay range between requests.
- If you upload 150–200 companies, expect the runtime to scale linearly. You can speed up by lowering `max_results` and `min_delay`/`max_delay` in the UI.
- If you previously got an error at "line 7" in older code, it was likely `from googlesearch import search`. That's replaced here with `from duckduckgo_search import ddg` to avoid that import issue.

"""

import streamlit as st
import pandas as pd
import requests
import re
import time
import random
import io
from bs4 import BeautifulSoup
from duckduckgo_search import ddg
from urllib.parse import urlparse

# -------------------------- Utility functions --------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
]

PHONE_RE = re.compile(r'(?:\+?\d{1,3}[\s.\-])?(?:\(?\d{2,4}\)?[\s.\-])?\d{3,4}[\s.\-]\d{3,4}')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def get_domain(url):
    try:
        p = urlparse(url)
        return p.netloc.lower().lstrip('www.')
    except Exception:
        return url


def nice_join(lst):
    if not lst:
        return ""
    return ", ".join(sorted(set(lst)))


def extract_contacts_from_html(soup):
    """Extract emails/phones from BeautifulSoup object."""
    emails = set()
    phones = set()

    # mailto / tel links
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('mailto:'):
            emails.add(href.split(':', 1)[1].split('?')[0])
        if href.startswith('tel:'):
            phones.add(href.split(':', 1)[1])

    text = soup.get_text(' ', strip=True)
    emails.update(EMAIL_RE.findall(text))
    phones.update(PHONE_RE.findall(text))

    # Clean phones: remove long whitespace and trailing characters
    cleaned_phones = set()
    for ph in phones:
        ph_clean = re.sub(r"[\s.\-()]+", ' ', ph).strip()
        cleaned_phones.add(ph_clean)

    return list(emails), list(cleaned_phones)


# -------------------------- Core scraping functions --------------------------

def find_candidate_urls(company, max_results=8):
    """Use DuckDuckGo to get candidate pages for the company. Returns unique URLs with contact/about prioritized."""
    query = f"{company} contact OR about OR \"contact us\" OR \"about us\""
    try:
        results = ddg(query, max_results=max_results) or []
    except Exception:
        results = []

    urls = []
    seen = set()
    # ddg returns list of dicts with 'href' key in many installs; sometimes 'url' or 'link' -> handle both
    for r in results:
        url = r.get('href') or r.get('url') or r.get('link') or ''
        if not url:
            continue
        domain = get_domain(url)
        if domain in seen:
            continue
        seen.add(domain)
        urls.append(url)

    # Add the root domain URLs as fallback (e.g., https://company.com)
    root_urls = []
    for u in urls:
        try:
            p = urlparse(u)
            root = f"{p.scheme}://{p.netloc}" if p.scheme else f"https://{p.netloc}"
            if root not in seen:
                root_urls.append(root)
                seen.add(root)
        except Exception:
            pass

    # prioritize URLs that likely contain contact info
    prioritized = [u for u in urls if 'contact' in u.lower() or 'about' in u.lower()]
    others = [u for u in urls if u not in prioritized]
    final = prioritized + others + root_urls

    # ensure uniqueness
    unique_final = []
    seen2 = set()
    for u in final:
        if u in seen2:
            continue
        seen2.add(u)
        unique_final.append(u)

    return unique_final[:max_results]


def extract_contacts(url, session, headers):
    """Fetch a URL and extract contacts using BeautifulSoup."""
    try:
        resp = session.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return [], []
        soup = BeautifulSoup(resp.text, 'html.parser')
        return extract_contacts_from_html(soup)
    except Exception:
        return [], []


def scrape_company(company, session, max_results=6, min_delay=3.0, max_delay=6.0):
    """For a single company, find candidate pages and extract contacts."""
    candidate_urls = find_candidate_urls(company, max_results=max_results)
    found_emails = set()
    found_phones = set()
    sources = []

    for url in candidate_urls:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        emails, phones = extract_contacts(url, session, headers)
        if emails or phones:
            found_emails.update(emails)
            found_phones.update(phones)
            sources.append(url)
        # delay between requests
        time.sleep(random.uniform(min_delay, max_delay))

    return {
        'Company': company,
        'Emails': nice_join(found_emails),
        'Phones': nice_join(found_phones),
        'Sources': nice_join(sources)
    }


# -------------------------- Streamlit UI --------------------------

st.set_page_config(page_title='Company Contact Finder', layout='wide')
st.title('📇 Company Contact Finder — Colab-style (Accurate)')

with st.sidebar:
    st.markdown('**Bulk settings**')
    max_results = st.number_input('Max search results per company', min_value=1, max_value=20, value=6)
    min_delay = st.number_input('Min delay (seconds) between requests', min_value=0.5, max_value=30.0, value=2.0)
    max_delay = st.number_input('Max delay (seconds) between requests', min_value=0.5, max_value=60.0, value=4.0)
    if max_delay < min_delay:
        st.error('Max delay must be >= Min delay')

st.markdown(
    'Paste a single company name below **or** upload a CSV/XLSX with one column of company names (column name `company` or first column used).'
)

single_company = st.text_input('Single company name (optional)')
uploaded_file = st.file_uploader('Upload CSV or XLSX (optional) — one column with company names', type=['csv', 'xlsx'])

start = st.button('Start Scraping')

if start:
    # build the company list
    companies = []
    if single_company and single_company.strip():
        companies = [single_company.strip()]
    elif uploaded_file is not None:
        try:
            if uploaded_file.name.lower().endswith('.csv'):
                df_in = pd.read_csv(uploaded_file)
            else:
                df_in = pd.read_excel(uploaded_file)
            # find column named "company" (case-insensitive) else take first column
            cols = df_in.columns.tolist()
            candidate_col = None
            for c in cols:
                if str(c).strip().lower() == 'company':
                    candidate_col = c
                    break
            if candidate_col is None:
                candidate_col = cols[0]
            companies = df_in[candidate_col].dropna().astype(str).str.strip().tolist()
        except Exception as e:
            st.error(f'Could not read uploaded file: {e}')
            companies = []
    else:
        st.error('Please enter a company name or upload a file.')

    if companies:
        session = requests.Session()
        results = []

        progress_bar = st.progress(0)
        status_text = st.empty()

        total = len(companies)
        for idx, comp in enumerate(companies, start=1):
            status_text.info(f'[{idx}/{total}] Scraping: {comp}')
            row = scrape_company(comp, session, max_results=max_results, min_delay=float(min_delay), max_delay=float(max_delay))
            results.append(row)
            progress_bar.progress(int((idx / total) * 100))

        df_out = pd.DataFrame(results)

        st.success('Scraping completed — results below')
        st.dataframe(df_out)

        # CSV download
        csv_bytes = df_out.to_csv(index=False).encode('utf-8')
        st.download_button('Download CSV', data=csv_bytes, file_name='company_contacts.csv', mime='text/csv')

        # Excel download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_out.to_excel(writer, index=False, sheet_name='contacts')
        output.seek(0)
        st.download_button('Download Excel (.xlsx)', data=output, file_name='company_contacts.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        # small summary
        total_emails = df_out['Emails'].str.len().sum() if 'Emails' in df_out.columns else 0
        st.write(f'Companies scraped: {total} — Rows with at least one contact: {(df_out[['Emails','Phones']].apply(lambda r: bool(r['Emails'] or r['Phones']), axis=1)).sum()}')

        st.info('Tip: If you upload a large list (150-200 names), consider reducing "Max search results" and delay values to speed up the run. You can also run this in Colab or a cloud VM if you want uninterrupted long runs.')

else:
    st.info('Enter a company name or upload a CSV/XLSX and click Start Scraping.')

# -------------------------- End --------------------------
