"""
Streamlit Contact Scraper
---------------------------------
Goal: Upload an Excel file of company names, find official websites via Google Search,
scrape emails & phone numbers from homepage/contact pages, show live progress & logs,
allow cancellation, and download results as Excel — all with clean UI & robust errors.

Required packages (add these to requirements.txt):
streamlit
pandas
requests
beautifulsoup4
openpyxl
googlesearch-python

Run locally:
  streamlit run app.py

Safety & Respect:
- Be mindful of target sites' robots/terms. Use conservative delays to avoid hammering.
- Only use the data for legitimate purposes and comply with local laws (e.g., GDPR/DPDP).
"""

from __future__ import annotations

import re
import time
import random
from io import BytesIO
from typing import List, Tuple, Optional, Dict, Set
from urllib.parse import urlparse, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

# =============================
# ------- UI SETTINGS ---------
# =============================
st.set_page_config(
    page_title="Contact Scraper",
    page_icon="📇",
    layout="wide",
)

# Minimal, clean styling
st.markdown(
    """
    <style>
        .main > div { padding-top: 0rem; }
        [data-testid="stSidebar"] { width: 360px; }
        .small { font-size: 0.88rem; color: #5c5f66; }
        .logbox { background: #0f1115; color: #d9d9e3; padding: 12px 14px; border-radius: 12px; min-height: 180px; }
        .ok    { color: #22c55e; }
        .warn  { color: #f59e0b; }
        .err   { color: #ef4444; }
        .muted { color: #9aa0a6; }
        .pill  { display:inline-block; padding: 2px 8px; border-radius: 999px; background:#eef2ff; color:#3730a3; font-size: 0.75rem; margin-left: 6px; }
        .tight { margin-top: -6px; }
        .stButton > button { border-radius: 12px; }
        .status-card { border-radius: 16px; padding: 12px; border: 1px solid #e6e8eb; background: #fafafa; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================
# ------- SESSION STATE -------
# =============================
if "df" not in st.session_state:
    st.session_state.df: Optional[pd.DataFrame] = None
if "results" not in st.session_state:
    st.session_state.results: Optional[pd.DataFrame] = None
if "running" not in st.session_state:
    st.session_state.running: bool = False
if "stop_flag" not in st.session_state:
    st.session_state.stop_flag: bool = False
if "log_lines" not in st.session_state:
    st.session_state.log_lines: List[str] = []
if "progress_val" not in st.session_state:
    st.session_state.progress_val: int = 0

# =============================
# ---------- HELPERS ----------
# =============================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQ_TIMEOUT = 15  # seconds
DELAY_RANGE = (1.2, 2.4)  # polite delay between requests

# Common non-official domains to avoid picking as the company website
BLACKLIST_DOMAINS = {
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "wikipedia.org", "bloomberg.com", "crunchbase.com", "pitchbook.com",
    "youtube.com", "medium.com", "github.com", "indeed.com", "glassdoor.com",
    "google.com", "maps.google.", "g2.com"
}

CONTACT_HINTS = ("contact", "contact-us", "kontakt", "impressum", "about", "support")


def ui_log(msg: str, level: str = "info") -> None:
    """Append a line to the UI log and render it."""
    prefix = {"info": "•", "ok": "✓", "warn": "⚠", "err": "✗"}.get(level, "•")
    css = {"info": "muted", "ok": "ok", "warn": "warn", "err": "err"}.get(level, "muted")
    st.session_state.log_lines.append(f"<span class='{css}'>{prefix} {msg}</span>")


def render_log_area(container):
    html = "<br>".join(st.session_state.log_lines[-400:]) or "<span class='muted'>Logs will appear here…</span>"
    container.markdown(f"<div class='logbox'>{html}</div>", unsafe_allow_html=True)


def read_company_list(file) -> List[str]:
    try:
        df = pd.read_excel(file)
    except Exception as e:
        raise ValueError(f"Failed to read Excel: {e}")

    if df.shape[1] < 1:
        raise ValueError("Excel must have at least 1 column with company names in the first column.")

    first_col = df.columns[0]
    companies = [str(x).strip() for x in df[first_col].dropna().astype(str).tolist()]
    companies = [c for c in companies if c and c.lower() != "nan"]

    if not companies:
        raise ValueError("No company names found in the first column.")

    st.session_state.df = df
    return companies


def google_search(query: str, max_results: int = 8) -> List[str]:
    """Return a list of URL strings from Google Search using the 'googlesearch' lib.
    Works with either API style (num_results) or (num/stop/pause).
    """
    try:
        from googlesearch import search  # type: ignore
    except Exception as e:
        ui_log("googlesearch package missing. Add 'googlesearch-python' to requirements.txt.", "err")
        return []

    try:
        # Newer API
        results = list(search(query, num_results=max_results, lang="en"))
    except TypeError:
        # Older API fallback
        results = list(search(query, num=max_results, stop=max_results, pause=2.0))
    except Exception as e:
        ui_log(f"Google search failed: {e}", "err")
        return []

    # Basic cleaning
    cleaned = []
    for u in results:
        if isinstance(u, bytes):
            u = u.decode("utf-8", errors="ignore")
        cleaned.append(str(u))
    return cleaned


def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def looks_official(url: str, company: str) -> bool:
    d = domain_of(url)
    if not d:
        return False
    # Avoid big directories/aggregators
    if any(b in d for b in BLACKLIST_DOMAINS):
        return False
    # Heuristic: domain should roughly contain a key token from company name
    key = re.sub(r"[^a-z0-9]", "", company.lower())[:12]
    token_hits = sum(1 for t in re.split(r"\W+", company.lower()) if t and t in d)
    if key and (key in d or token_hits >= 1):
        return True
    # Fallback: if not blacklisted and not a known aggregator, still allow as candidate
    return True


def pick_official_candidate(urls: List[str], company: str) -> Optional[str]:
    # Filter by heuristics and prefer shorter path (homepage-like)
    candidates = [u for u in urls if looks_official(u, company)]
    if not candidates:
        return None
    candidates.sort(key=lambda u: (len(urlparse(u).path or "/"), len(u)))
    return candidates[0]


def http_get(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQ_TIMEOUT)
        if r.status_code >= 400:
            return None
        # Some sites compress or use encodings oddly
        r.encoding = r.apparent_encoding or r.encoding
        return r.text
    except Exception:
        return None


def find_contact_links(base_url: str, html: str) -> List[str]:
    links: Set[str] = set()
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = (a.get_text(strip=True) or "").lower()
            if any(h in href.lower() for h in CONTACT_HINTS) or any(h in text for h in CONTACT_HINTS):
                links.add(urljoin(base_url, href))
    except Exception:
        pass

    # Include direct guesses
    parsed = urlparse(base_url)
    guessed = [
        urljoin(f"{parsed.scheme}://{parsed.netloc}", "/contact"),
        urljoin(f"{parsed.scheme}://{parsed.netloc}", "/contact-us"),
        urljoin(f"{parsed.scheme}://{parsed.netloc}", "/about"),
        urljoin(f"{parsed.scheme}://{parsed.netloc}", "/support"),
    ]
    for g in guessed:
        links.add(g)
    return list(links)[:6]


def extract_emails(text: str, primary_domain: str | None) -> List[str]:
    if not text:
        return []
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    found = set(m.group(0).lower() for m in email_re.finditer(text))
    if primary_domain:
        filtered = {e for e in found if primary_domain in e.split("@")[-1]}
        if filtered:
            return sorted(filtered)[:20]
    return sorted(found)[:20]


def extract_phones(text: str) -> List[str]:
    if not text:
        return []
    # Broad international-ish phone regex with optional country code & extension
    phone_re = re.compile(r"""
        (?:\+\d{1,3}[\s\-]?)?                # country code
        (?:\(?\d{2,4}\)?[\s\-]?)?            # area code
        \d{3,4}[\s\-]?\d{3,4}                 # number blocks
        (?:\s*(?:ext\.?|x)\s*\d{1,5})?        # extension
    """, re.VERBOSE)
    raw = set(m.group(0) for m in phone_re.finditer(text))
    cleaned: Set[str] = set()
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if 7 <= len(digits) <= 15:  # plausible length
            # Normalize small formatting
            norm = re.sub(r"\s+", " ", p).strip()
            cleaned.add(norm)
    return sorted(cleaned)[:20]


def scrape_company(company: str) -> Dict[str, str]:
    """Process a single company: search, pick official site, fetch & extract contacts."""
    row = {
        "Company Name": company,
        "Website": "Not Found",
        "Emails": "",
        "Phones": "",
        "Status": ""
    }

    # Step 1: Search
    query = f"{company} official website"
    urls = google_search(query, max_results=8)
    time.sleep(random.uniform(*DELAY_RANGE))

    if st.session_state.stop_flag:
        row["Status"] = "Stopped"
        return row

    if not urls:
        row["Status"] = "No search results"
        return row

    candidate = pick_official_candidate(urls, company)
    if not candidate:
        row["Status"] = "No suitable candidate"
        return row

    # Step 2: Fetch homepage
    homepage = candidate
    html_home = http_get(homepage)
    time.sleep(random.uniform(*DELAY_RANGE))

    if st.session_state.stop_flag:
        row["Status"] = "Stopped"
        return row

    if not html_home:
        row["Website"] = homepage
        row["Status"] = "Homepage unreachable"
        return row

    row["Website"] = homepage
    base_domain = domain_of(homepage)

    # Step 3: Extract from homepage
    emails: Set[str] = set(extract_emails(html_home, base_domain))
    phones: Set[str] = set(extract_phones(html_home))

    # Step 4: Try contact/about pages
    for link in find_contact_links(homepage, html_home):
        if st.session_state.stop_flag:
            row["Status"] = "Stopped"
            break
        html = http_get(link)
        time.sleep(random.uniform(*DELAY_RANGE))
        if not html:
            continue
        emails.update(extract_emails(html, base_domain))
        phones.update(extract_phones(html))

    row["Emails"] = ", ".join(sorted(emails))
    row["Phones"] = ", ".join(sorted(phones))

    if not emails and not phones:
        row["Status"] = "No contacts found"
    else:
        row["Status"] = "OK"
    return row


# =============================
# ------------ UI -------------
# =============================

st.title("📇 Contact Scraper — Streamlit")
st.caption("Upload → Extract → Review → Download. Built for accuracy with polite delays and clear logs.")

with st.sidebar:
    st.header("How it works")
    st.markdown(
        """
        1. **Upload** an Excel (.xlsx) with company names in the **first column**.
        2. Click **Start Extraction**.
        3. Watch **progress and logs** in real time.
        4. Click **Stop Extraction** anytime to halt gracefully.
        5. **Download** results as Excel when done.
        """
    )
    st.markdown("---")
    st.subheader("Tips")
    st.markdown(
        """
        - Keep company names clean (no extra punctuation).
        - Results prioritize the official domain and filter unrelated emails.
        - If searches get blocked, **Stop**, wait a bit, and try again.
        - Be patient: searches use short, polite delays.
        """
    )

col_left, col_right = st.columns([1.15, 1])

with col_left:
    st.markdown("### 1) Upload Excel")
    uploaded = st.file_uploader("Excel file (.xlsx)", type=["xlsx"], accept_multiple_files=False)

    # Sample template download
    sample_df = pd.DataFrame({"Company Name": ["Widget Inc", "ACME Corp", "Globex" ]})
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        sample_df.to_excel(writer, index=False)
    st.download_button(
        "Download sample template",
        buf.getvalue(),
        file_name="sample_companies.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Excel with a single column: Company Name"
    )

    st.markdown("### 2) Controls")
    cols = st.columns(3)
    with cols[0]:
        start_clicked = st.button("▶ Start Extraction", type="primary", use_container_width=True, disabled=st.session_state.running)
    with cols[1]:
        stop_clicked = st.button("⛔ Stop Extraction", use_container_width=True)
    with cols[2]:
        reset_clicked = st.button("↺ Reset", use_container_width=True, help="Clear logs & results")

    if reset_clicked:
        st.session_state.running = False
        st.session_state.stop_flag = False
        st.session_state.results = None
        st.session_state.log_lines = []
        st.session_state.progress_val = 0
        ui_log("Reset complete.", "ok")

    if stop_clicked:
        st.session_state.stop_flag = True
        ui_log("Stop requested. Finishing current step…", "warn")

with col_right:
    st.markdown("### Status & Progress")
    status_container = st.container()
    progress = st.progress(st.session_state.progress_val)
    log_container = st.container()
    render_log_area(log_container)

# ============== Extraction Runner ==============

def run_extraction(companies: List[str]):
    total = len(companies)
    st.session_state.results = pd.DataFrame(columns=["Company Name", "Website", "Emails", "Phones", "Status"])
    st.session_state.progress_val = 0

    # Use st.status if available; otherwise fallback to container updates
    use_status = hasattr(st, "status")

    if use_status:
        with st.status("Working…", expanded=True) as s:
            for idx, company in enumerate(companies, start=1):
                if st.session_state.stop_flag:
                    s.update(label="Stopped by user", state="error")
                    break
                ui_log(f"Searching: <b>{company}</b>")
                row = scrape_company(company)
                st.session_state.results.loc[len(st.session_state.results)] = row

                st.session_state.progress_val = int(idx / total * 100)
                progress.progress(st.session_state.progress_val)
                render_log_area(log_container)

                s.update(label=f"Processing {idx}/{total}: {company}")

            if not st.session_state.stop_flag:
                s.update(label="Extraction complete", state="complete")
    else:
        # Fallback if st.status not available
        status_container.markdown("<div class='status-card'>Working…</div>", unsafe_allow_html=True)
        for idx, company in enumerate(companies, start=1):
            if st.session_state.stop_flag:
                status_container.markdown("<div class='status-card err'>Stopped by user</div>", unsafe_allow_html=True)
                break
            ui_log(f"Searching: <b>{company}</b>")
            row = scrape_company(company)
            st.session_state.results.loc[len(st.session_state.results)] = row

            st.session_state.progress_val = int(idx / total * 100)
            progress.progress(st.session_state.progress_val)
            render_log_area(log_container)
            status_container.markdown(
                f"<div class='status-card'>Processing {idx}/{total}: <b>{company}</b></div>",
                unsafe_allow_html=True,
            )
        if not st.session_state.stop_flag:
            status_container.markdown("<div class='status-card ok'>Extraction complete</div>", unsafe_allow_html=True)


# Handle Start Extraction
if start_clicked and not st.session_state.running:
    # Validate file
    if not uploaded:
        st.error("Please upload an Excel (.xlsx) file with company names in the first column.")
    else:
        try:
            companies = read_company_list(uploaded)
            ui_log(f"Uploaded file: <b>{getattr(uploaded, 'name', 'uploaded.xlsx')}</b>", "ok")
            ui_log(f"Found <b>{len(companies)}</b> company names.", "ok")

            st.session_state.running = True
            st.session_state.stop_flag = False

            run_extraction(companies)

            st.session_state.running = False
            if st.session_state.stop_flag:
                ui_log("Stopped by user. Partial results are available below.", "warn")
            else:
                ui_log("All done! You can download the results as Excel.", "ok")
        except Exception as e:
            st.session_state.running = False
            ui_log(f"Error: {e}", "err")
            st.error(
                "There was a problem reading the file or during extraction. "
                "Please check the template and try again."
            )

# ============== Results & Download ==============

st.markdown("### 3) Results")
if st.session_state.results is not None and not st.session_state.results.empty:
    st.dataframe(st.session_state.results, use_container_width=True, hide_index=True)

    # Prepare Excel for download
    out_buf = BytesIO()
    with pd.ExcelWriter(out_buf, engine="openpyxl") as writer:
        st.session_state.results.to_excel(writer, index=False)

    st.download_button(
        label="⬇ Download results (Excel)",
        data=out_buf.getvalue(),
        file_name="contact_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Company, Website, Emails, Phones, Status"
    )
else:
    st.caption("Results will appear here after extraction.")

# Footer note
st.markdown("""
<div class='tight small'>
<b>Notes.</b> This tool uses best-effort heuristics. If a site blocks bots or requires JS, results may be limited. 
Use responsibly and consider adding API keys/a headless browser for tougher targets.
</div>
""", unsafe_allow_html=True)
