import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import random

# UTILITIES

EMAIL_REGEX = r"(?:[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*|\"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*\")@(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}"
PHONE_REGEX = r"(?:\+\d{1,3}\s*)?(?:\(?\d{2,5}\)?\s*|\d{2,5}\s*)(?:[\s\-]?\d{3,5}){2,3}"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
    # Add several realistic user-agent strings
]

# Use your Google API key if available, otherwise fallback to scraping Google SERP
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"] if "GOOGLE_API_KEY" in st.secrets else None
GOOGLE_CSE_ID = st.secrets["GOOGLE_CSE_ID"] if "GOOGLE_CSE_ID" in st.secrets else None

@st.cache_data(show_spinner=False)
def cached_scrape(url):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""

def extract_contacts(text):
    emails = list(set(re.findall(EMAIL_REGEX, text, re.IGNORECASE)))
    phones = list(set(re.findall(PHONE_REGEX, text)))
    return emails, phones

def get_contact_links(base_url, soup):
    links = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        for kw in ['contact', 'about']:
            if kw in href.lower():
                full_url = urljoin(base_url, href)
                links.add(full_url)
    return list(links)

def search_official_website(company_name):
    if GOOGLE_API_KEY and GOOGLE_CSE_ID:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": company_name,
            "num": 3
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            results = response.json().get("items", [])
            for result in results:
                site = result.get("link", "")
                if site and not re.search(r"(linkedin|crunchbase|facebook|twitter|instagram|wikipedia)", site, re.I):
                    return site
    else:
        # Fallback: scrape Google (unstable, use a paid API for production where possible)
        query = f"{company_name} official site"
        url = "https://www.google.com/search"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        params = {"q": query}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")
            for cite in soup.select("a"):
                href = cite.get("href", "")
                if href.startswith("http") and not re.search(r"(linkedin|crunchbase|facebook|twitter|instagram|wikipedia)", href, re.I):
                    netloc = urlparse(href).netloc
                    if netloc and not netloc.endswith("google.com"):
                        return href
        except Exception:
            return ""
    return ""

def scrape_company_info(company):
    time.sleep(random.uniform(1.5, 3.5))  # Pause to avoid rate-limiting
    website = search_official_website(company)
    if not website:
        return {"Company": company, "Website": "Not Found", "Emails": "Not Found", "Phones": "Not Found"}
    raw_html = cached_scrape(website)
    emails, phones = extract_contacts(raw_html)
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        contact_links = get_contact_links(website, soup)
        for link in contact_links[:3]:
            html = cached_scrape(link)
            e2, p2 = extract_contacts(html)
            emails.extend(e2)
            phones.extend(p2)
    except Exception:
        pass
    emails = list(set(emails))
    phones = list(set(phones))
    return {
        "Company": company,
        "Website": website,
        "Emails": ", ".join(emails) if emails else "Not Found",
        "Phones": ", ".join(phones) if phones else "Not Found"
    }

# ---- STREAMLIT UI ----

st.set_page_config(page_title="Company Contact Scraper", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    .stApp { background-color: #f6f8fa; }
    .css-1cpxqw2 { font-family: 'Inter', sans-serif; }
    .stButton>button { background-color: #244E6A; color: white; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Company Contact Scraper 🏢")
st.write("Upload a CSV/Excel file of company names. The app will find official company sites and extract emails/phones from their web pages. [Production Ready]")

# Upload Section
uploaded_file = st.file_uploader("Upload Excel or CSV (with company names)", type=["csv", "xlsx"], key="uploader", help="Make sure your file has a column for company names.")
reset_trigger = st.button("Reload / Reset", key="reset_button")

# Keep session state for results
if 'results' not in st.session_state or reset_trigger:
    st.session_state.results = None
    st.session_state.df = None

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception:
        st.error("Could not parse file. Please check file format and columns.")
        st.stop()

    # Detect company column
    company_col = None
    for col in df.columns:
        if "company" in col.lower():
            company_col = col
            break
    if company_col is None:
        st.error("No column labelled for company names. Please check your file.")
        st.stop()

    companies = df[company_col].dropna().astype(str).unique().tolist()
    st.info(f"Found {len(companies)} unique companies to process.")

    # Main scraping logic – multiparallel for efficiency
    MAX_THREADS = min(12, len(companies))
    task_state = st.empty()
    results_list = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_company = {executor.submit(scrape_company_info, company): company for company in companies}
        for i, future in enumerate(as_completed(future_to_company), 1):
            result = future.result()
            results_list.append(result)
            task_state.info(f"Processed {i}/{len(companies)} companies.")

    st.session_state.results = results_list
    st.session_state.df = pd.DataFrame(results_list)

if st.session_state.results:
    st.success("Scraping Complete!")
    st.dataframe(st.session_state.df)

    # Download Output
    output = st.session_state.df
    output_file = output.to_excel(index=False, engine="openpyxl")
    st.download_button(
        "Download Results (Excel file)",
        data=output_file,
        file_name="company_contacts.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.caption("Company | Website | Emails | Phones. Enjoy your contact leads!")

# Deployment extra for platforms like Render/Heroku
import os
if "0.0.0.0" in os.environ.get("BIND_ON", ""):
    from streamlit.web import cli as stcli
    if __name__ == "__main__":
        import sys
        sys.argv = ["streamlit", "run", sys.argv[0], "--server.address=0.0.0.0", "--server.port=8501"]
        sys.exit(stcli.main())
