"""
Streamlit Contact Scraper (production-friendly)

How to use:
1) Install dependencies: pip install streamlit pandas requests beautifulsoup4 openpyxl
2) Run locally: streamlit run streamlit_contact_scraper.py
3) (Optional) Provide a SerpAPI key in the sidebar for robust website search (recommended for production).

Notes:
- This app uses multiple techniques to locate the official website: SerpAPI (if provided), googlesearch (if installed), and DuckDuckGo HTML fallback.
- Scraping is parallelized with a bounded ThreadPoolExecutor. Per-domain polite delays, randomized user-agents and retries help reduce blocking.
- Still: scraping other sites can be blocked. For the most reliable production behavior use a paid search API (SerpAPI/Google Custom Search).

Author: Generated for Manish
"""

import streamlit as st
import pandas as pd
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import io

# -------------------------- Configuration / constants --------------------------
USER_AGENTS = [
    # A short list of commonly-used desktop user agents. Rotate these.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+\d{1,3}[\s\-]?)?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}")

# Avoid scraping these aggregator domains when guessing website
AGGREGATOR_DOMAIN_PARTS = [
    "linkedin", "facebook", "crunchbase", "glassdoor", "yellowpages", "yelp", "wikipedia",
]

# -------------------------- Utility functions --------------------------

def create_session(timeout=10):
    """Create a requests.Session with retry strategy."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.7, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
    session.timeout = timeout
    return session


@st.cache_data(show_spinner=False)
def normalize_company_name(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z ]+", " ", str(name)).strip()


# -------------------------- Website discovery --------------------------

@st.cache_data(show_spinner=False)
def find_website_serpapi(company: str, serpapi_key: str):
    """Try SerpAPI (most robust) if user provides a key."""
    try:
        params = {
            "engine": "google",
            "q": f"{company} official site",
            "api_key": serpapi_key,
            "num": 5,
        }
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=10)
        data = resp.json()
        # serpapi returns `organic_results`
        for item in data.get("organic_results", []):
            link = item.get("link") or item.get("url")
            if link:
                # prefer a link that looks like the official site (not linkedin etc.)
                if not any(p in link for p in AGGREGATOR_DOMAIN_PARTS):
                    return link
        # fallback to first organic
        if data.get("organic_results"):
            return data["organic_results"][0].get("link")
    except Exception:
        return None
    return None


@st.cache_data(show_spinner=False)
def find_website_duckduckgo(company: str):
    """Fallback search using DuckDuckGo HTML front-end and parse links.
    This is best-effort and may break if DuckDuckGo changes markup.
    """
    try:
        query = quote_plus(f"{company} official site")
        url = f"https://duckduckgo.com/html/?q={query}"
        session = create_session()
        resp = session.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        # look for external links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # duckduckgo uses /l/?kh=1&uddg=<urlencoded-url> sometimes
            if "uddg=" in href:
                # extract last param
                parsed = href.split("uddg=")[-1]
                try:
                    candidate = requests.utils.unquote(parsed)
                except Exception:
                    candidate = parsed
            elif href.startswith("http"):
                candidate = href
            else:
                continue
            # filter out aggregators
            if any(p in candidate for p in AGGREGATOR_DOMAIN_PARTS):
                continue
            return candidate
    except Exception:
        return None
    return None


@st.cache_data(show_spinner=False)
def find_website_googlesearch(company: str):
    """Try the `googlesearch` python library (if installed in the environment).
    Not guaranteed in all deployments; provided as an optional extra.
    """
    try:
        from googlesearch import search
        query = f"{company} official site"
        for url in search(query, num=5, stop=5, pause=1.5):
            if not any(p in url for p in AGGREGATOR_DOMAIN_PARTS):
                return url
    except Exception:
        return None
    return None


def find_website(company: str, serpapi_key: str | None):
    """Top-level website lookup: SerpAPI -> googlesearch -> DuckDuckGo fallback
    Cached wrappers above will limit re-requests.
    """
    company = normalize_company_name(company)
    if serpapi_key:
        result = find_website_serpapi(company, serpapi_key)
        if result:
            return result
    # try googlesearch package
    try:
        result = find_website_googlesearch(company)
        if result:
            return result
    except Exception:
        pass
    # finally ddg fallback
    result = find_website_duckduckgo(company)
    return result


# -------------------------- Contact extraction --------------------------

@st.cache_data(show_spinner=False)
def extract_contacts_from_url(url: str, max_pages: int = 3, timeout: int = 8):
    """Given a starting URL (homepage), fetch page and candidate 'contact/about' pages and extract emails/phones.
    Caching helps if multiple companies share domains.
    """
    session = create_session(timeout=timeout)
    emails = set()
    phones = set()

    def try_fetch(u):
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            r = session.get(u, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.text:
                return r.text
        except Exception:
            return None
        return None

    # Normalize URL
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "http://" + url

    # 1) Try homepage
    front = try_fetch(url)
    if front:
        soup = BeautifulSoup(front, "html.parser")
        text = soup.get_text(" ")
        emails.update(EMAIL_RE.findall(text))
        phones.update(PHONE_RE.findall(text))
        # mailto links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                addr = href.split("mailto:")[-1].split("?")[0]
                if EMAIL_RE.match(addr):
                    emails.add(addr)

        # find candidate contact/about links
        candidates = []
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if any(k in href for k in ["/contact", "contactus", "contact-us", "about", "about-us", "support", "help", "reach-us"]):
                full = urljoin(url, a["href"])
                candidates.append(full)

        # Deduplicate and limit
        candidates = list(dict.fromkeys(candidates))[:max_pages]

        # visit candidate pages
        for c in candidates:
            time.sleep(random.uniform(0.3, 1.0))
            page = try_fetch(c)
            if page:
                s2 = BeautifulSoup(page, "html.parser")
                t2 = s2.get_text(" ")
                emails.update(EMAIL_RE.findall(t2))
                phones.update(PHONE_RE.findall(t2))
                for a in s2.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith("mailto:"):
                        addr = href.split("mailto:")[-1].split("?")[0]
                        if EMAIL_RE.match(addr):
                            emails.add(addr)
    # Post-process phones: PHONE_RE returns tuples; flatten
    phone_strings = set()
    for p in phones:
        if isinstance(p, tuple):
            phone_strings.add("".join(p))
        else:
            phone_strings.add(p)

    # clean results
    clean_emails = sorted({e.strip().lower() for e in emails})
    clean_phones = sorted({re.sub(r"\s+", " ", p).strip() for p in phone_strings})
    return clean_emails, clean_phones


# -------------------------- Worker & orchestration --------------------------

def process_company(company: str, serpapi_key: str | None, per_request_delay_range=(0.3, 1.0)):
    """Full pipeline for a single company: find website then extract contacts."""
    company_norm = normalize_company_name(company)
    website = find_website(company_norm, serpapi_key)
    # polite random delay before scraping target site
    time.sleep(random.uniform(*per_request_delay_range))
    emails, phones = ([], [])
    if website:
        try:
            emails, phones = extract_contacts_from_url(website)
        except Exception:
            emails, phones = ([], [])
    else:
        website = "Not Found"
    return {
        "Company": company,
        "Website": website,
        "Emails": "; ".join(emails) if emails else "",
        "Phones": "; ".join(phones) if phones else "",
    }


# -------------------------- Streamlit UI --------------------------

st.set_page_config(page_title="Company Contact Scraper", layout="wide")
st.title("Company Contact Scraper — Streamlined for Team Use")
st.markdown(
    "Simple, production-minded Streamlit app to locate company websites and extract emails & phone numbers. For best reliability provide a SerpAPI key in the sidebar (optional)."
)

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    serpapi_key = st.text_input("SerpAPI API key (optional)", type="password")
    max_workers = st.number_input("Max parallel workers (threads)", min_value=1, max_value=20, value=6, step=1)
    per_request_min = st.number_input("Min per-site delay (s)", min_value=0.0, max_value=10.0, value=0.3, step=0.1)
    per_request_max = st.number_input("Max per-site delay (s)", min_value=0.0, max_value=10.0, value=1.0, step=0.1)
    timeout = st.number_input("HTTP timeout (s)", min_value=2, max_value=60, value=10, step=1)
    max_pages_to_check = st.number_input("Max contact/about pages to visit per site", min_value=1, max_value=10, value=3, step=1)
    st.markdown("---")
    st.caption("Tip: For heavier usage, use SerpAPI (paid) for reliable search results and fewer blocks.")


# File upload and reload/reset
uploaded_file = st.file_uploader("Upload Excel or CSV with company names (first column by default)", type=["xlsx", "xls", "csv"], accept_multiple_files=False)
if "df_uploaded" not in st.session_state:
    st.session_state.df_uploaded = None

if st.button("Reload / Reset"):
    st.session_state.df_uploaded = None
    st.experimental_rerun()

if uploaded_file is not None:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Could not read the uploaded file: {e}")
        st.stop()

    st.session_state.df_uploaded = df

# If no file in session state, show placeholder and stop
if st.session_state.df_uploaded is None:
    st.info("Upload a file to begin. You can upload an Excel/CSV file with a column of company names.")
    st.stop()

# file loaded
df_in = st.session_state.df_uploaded.copy()
st.subheader("Preview of uploaded data")
st.dataframe(df_in.head())

# Ask user which column contains company names
col_options = list(df_in.columns)
company_col = st.selectbox("Which column contains company names?", options=col_options, index=0)
companies = df_in[company_col].astype(str).fillna("").tolist()

start = st.button("Start Scraping")

if start:
    if not companies:
        st.error("No companies found in the selected column.")
        st.stop()

    # prepare results DataFrame
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_area = st.empty()

    total = len(companies)
    completed = 0

    # We'll use ThreadPoolExecutor with bounded workers
    with ThreadPoolExecutor(max_workers=int(max_workers)) as executor:
        futures = {}
        for idx, company in enumerate(companies):
            futures[executor.submit(process_company, company, serpapi_key, (per_request_min, per_request_max))] = (idx, company)

        for fut in as_completed(futures):
            idx, company = futures[fut]
            try:
                row = fut.result()
            except Exception as e:
                row = {"Company": company, "Website": "Error", "Emails": "", "Phones": ""}
            results.append(row)
            completed += 1
            progress_bar.progress(completed / total)
            status_text.text(f"Processed {completed} of {total}: {company}")
            # show an updating table — show most recent results on top
            df_results = pd.DataFrame(results)
            results_area.dataframe(df_results)

    # final table
    df_results = pd.DataFrame(results)
    st.success("Scraping complete")
    st.dataframe(df_results)

    # Merge back into original file (append columns)
    out_df = df_in.copy()
    out_df["_scraper_website"] = df_results["Website"]
    out_df["_scraper_emails"] = df_results["Emails"]
    out_df["_scraper_phones"] = df_results["Phones"]

    # Provide download as excel
    towrite = io.BytesIO()
    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
        out_df.to_excel(writer, index=False, sheet_name="contacts")
    towrite.seek(0)
    st.download_button("Download results as Excel", data=towrite, file_name="Company_Contacts.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # Also provide CSV
    st.download_button("Download results as CSV", data=out_df.to_csv(index=False).encode("utf-8"), file_name="Company_Contacts.csv", mime="text/csv")

    st.markdown("---")
    st.info("If you plan to run this often or for large lists, consider using SerpAPI and/or increasing polite delays to reduce blocks.")

    st.balloons()

# End of app
