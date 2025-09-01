"""
Simplified Streamlit Contact Scraper
---------------------------------
- Upload Excel file of company names (first column)
- Scrape emails & phones
- Show **progress bar only**
- Fast & simple (reduced delays)
- Download results as Excel
"""

import re
import time
import random
from io import BytesIO
from typing import List, Optional, Dict, Set
from urllib.parse import urlparse, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

st.set_page_config(page_title="Contact Scraper", page_icon="📇", layout="wide")

# =============================
# ------- SESSION STATE -------
# =============================
if "results" not in st.session_state:
    st.session_state.results: Optional[pd.DataFrame] = None
if "running" not in st.session_state:
    st.session_state.running: bool = False
if "stop_flag" not in st.session_state:
    st.session_state.stop_flag: bool = False
if "progress_val" not in st.session_state:
    st.session_state.progress_val: int = 0

# =============================
# ---------- HELPERS ----------
# =============================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"
REQ_TIMEOUT = 10


def read_company_list(file) -> List[str]:
    df = pd.read_excel(file)
    first_col = df.columns[0]
    companies = [str(x).strip() for x in df[first_col].dropna().tolist()]
    return companies


def google_search(query: str, max_results: int = 5) -> List[str]:
    try:
        from googlesearch import search
        return list(search(query, num_results=max_results, lang="en"))
    except Exception:
        return []


def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.replace("www.", "")
    except Exception:
        return ""


def http_get(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQ_TIMEOUT)
        if r.status_code < 400:
            r.encoding = r.apparent_encoding
            return r.text
    except Exception:
        return None
    return None


def extract_emails(text: str, domain: str) -> List[str]:
    if not text:
        return []
    regex = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    found = {m.group(0).lower() for m in regex.finditer(text)}
    if domain:
        domain_hits = {e for e in found if domain in e}
        if domain_hits:
            return list(domain_hits)
    return list(found)


def extract_phones(text: str) -> List[str]:
    if not text:
        return []
    
    # Regex: captures international (+XX) or local numbers with common separators
    regex = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}")
    found = {m.group(0).strip() for m in regex.finditer(text)}
    
    cleaned = []
    for num in found:
        digits = re.sub(r"\D", "", num)  # keep only digits
        # valid if length between 10–15 digits (most real phone numbers)
        if 10 <= len(digits) <= 15:
            normalized = re.sub(r"[\s.-]+", " ", num).strip()
            cleaned.append(normalized)
    
    # Deduplicate while preserving order
    seen = set()
    result = []
    for num in cleaned:
        if num not in seen:
            seen.add(num)
            result.append(num)
    
    return result


def scrape_company(company: str) -> Dict[str, str]:
    row = {"Company Name": company, "Website": "Not Found", "Emails": "", "Phones": ""}
    urls = google_search(company + " official website")
    if not urls:
        return row
    homepage = urls[0]
    html = http_get(homepage)
    if not html:
        row["Website"] = homepage
        return row
    row["Website"] = homepage
    dom = domain_of(homepage)
    emails = extract_emails(html, dom)
    phones = extract_phones(html)
    row["Emails"] = ", ".join(emails)
    row["Phones"] = ", ".join(phones)
    return row

# =============================
# ------------ UI -------------
# =============================
st.title("📇 Contact Scraper")
st.caption("Upload Excel → Extract contacts → Download results")

uploaded = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
start = st.button("▶ Start Extraction", type="primary")
stop = st.button("⛔ Stop")

if stop:
    st.session_state.stop_flag = True

progress = st.progress(st.session_state.progress_val)

if start and uploaded:
    companies = read_company_list(uploaded)
    results = []
    total = len(companies)
    st.session_state.stop_flag = False

    for idx, company in enumerate(companies, start=1):
        if st.session_state.stop_flag:
            break
        row = scrape_company(company)
        results.append(row)
        st.session_state.progress_val = int(idx / total * 100)
        progress.progress(st.session_state.progress_val)
        time.sleep(random.uniform(0.3, 0.8))  # quicker delay

    st.session_state.results = pd.DataFrame(results)

if st.session_state.results is not None and not st.session_state.results.empty:
    st.dataframe(st.session_state.results, use_container_width=True, hide_index=True)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        st.session_state.results.to_excel(writer, index=False)
    st.download_button(
        "⬇ Download results", buf.getvalue(), "contact_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
# --- RESET BUTTON ---
if st.button("🔄 Reset"):
    for key in ["uploaded_file", "results", "progress", "stop_flag"]:
        if key in st.session_state:
            del st.session_state[key]
    st.experimental_rerun()

