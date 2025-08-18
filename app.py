# app.py
# -----------------------------------------------------------
# Contact Scraper — Minimal, Robust, Error-Proof, Professional
# -----------------------------------------------------------

import os
import re
import time
import random
import logging
from io import BytesIO
from urllib.parse import urlparse, urljoin, unquote, parse_qs

import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------
# Basic Configuration
# --------------------
st.set_page_config(page_title="Contact Scraper — Minimal & Robust", layout="centered")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Hide Streamlit chrome (menu/footer) for a more "app-like" look
st.markdown(
    """
    <style>
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------
# App Constants
# -------------
# Balanced pacing — not too slow, not too quick
REQUEST_DELAY_MIN = 2.0    # seconds between individual HTTP requests
REQUEST_DELAY_MAX = 4.0

# Process in chunks so the STOP button works quickly between chunks
CHUNK_SIZE = 5             # companies per run before yielding & rerun
TABLE_REFRESH_EVERY = 20   # refresh the on-screen table every N rows

# Batch pacing to reduce block risk
BATCH_SIZE = 50
BATCH_PAUSE_MIN = 30       # seconds
BATCH_PAUSE_MAX = 60

# Block detection
CONSEC_BLOCK_THRESHOLD = 3  # if we detect 3 likely blocks in a row: show warning + pause

# DuckDuckGo HTML search pause
DDG_SEARCH_PAUSE = 1.0

# User-Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/94.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36",
]

BLACKLIST_PARTS = [
    "linkedin.", "facebook.", "twitter.", "instagram.", "youtube.",
    "crunchbase.", "zoominfo.", "glassdoor.", "yellowpages.", "yelp.",
    "wikipedia.", "bing.com", "google.com", "amazon."
]

BLOCK_PHRASES = [
    "unusual traffic", "recaptcha", "are you a robot",
    "verify you're a human", "sorry, you have been blocked"
]

# ----------------
# Helper Utilities
# ----------------
def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def is_blacklisted_domain(netloc: str) -> bool:
    netloc = netloc.lower()
    return any(b in netloc for b in BLACKLIST_PARTS)

def get_base_url(url: str) -> str | None:
    try:
        p = urlparse(url)
        scheme = p.scheme if p.scheme else "https"
        netloc = p.netloc if p.netloc else urlparse("https://" + url).netloc
        if not netloc:
            return None
        return f"{scheme}://{netloc}"
    except Exception:
        return None

def build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9"
    })
    return s

SESSION = build_session()

def polite_sleep(a=REQUEST_DELAY_MIN, b=REQUEST_DELAY_MAX):
    time.sleep(random.uniform(a, b))

# ----------------------
# Search Implementations
# ----------------------
def serpapi_key() -> str:
    return st.secrets.get("SERPAPI_KEY", os.environ.get("SERPAPI_KEY", ""))

def search_with_serpapi(query: str, num_results: int = 5) -> list[str]:
    key = serpapi_key()
    if not key:
        return []
    try:
        params = {"engine": "google", "q": query, "api_key": key, "num": num_results}
        resp = SESSION.get("https://serpapi.com/search.json", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        urls = []
        for r in data.get("organic_results", [])[:num_results]:
            link = r.get("link") or r.get("url")
            if link:
                urls.append(link)
        # light diversification
        for k in ("top_results", "related_questions"):
            for item in data.get(k, [])[:num_results]:
                link = item.get("link") or item.get("url")
                if link:
                    urls.append(link)
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out[:num_results]
    except Exception as e:
        logging.warning(f"SerpAPI search failed: {e}")
        return []

def search_with_duckduckgo_html(query: str, num_results: int = 5) -> list[str]:
    try:
        url = "https://html.duckduckgo.com/html/"
        data = {"q": query}
        resp = SESSION.post(url, data=data, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http"):
                links.append(href)
            elif "uddg=" in href:
                parsed = urlparse(href)
                qs = parse_qs(parsed.query)
                if "uddg" in qs:
                    try:
                        decoded = unquote(qs["uddg"][0])
                        links.append(decoded)
                    except Exception:
                        continue
        seen, out = set(), []
        for u in links:
            if u not in seen:
                seen.add(u)
                out.append(u)
            if len(out) >= num_results:
                break
        time.sleep(DDG_SEARCH_PAUSE)
        return out
    except Exception as e:
        logging.warning(f"DuckDuckGo search failed: {e}")
        return []

def get_company_search_results(company_name: str, max_results: int = 5) -> list[str]:
    query = f"{company_name} official website"
    urls = search_with_serpapi(query, num_results=max_results)
    if not urls:
        urls = search_with_duckduckgo_html(query, num_results=max_results)
    return urls

# ---------------------
# Contact Page Crawling
# ---------------------
def page_has_block(html_text: str) -> bool:
    low = html_text.lower()
    return any(sig in low for sig in BLOCK_PHRASES)

def extract_contacts_from_page(url: str) -> tuple[list[str], list[str], bool]:
    """Returns (emails, phones, blocked_detected)."""
    emails, phones = set(), set()
    blocked = False
    try:
        resp = SESSION.get(url, timeout=15)
        if resp is None or resp.status_code >= 400:
            return [], [], False
        html = resp.text
        if page_has_block(html):
            logging.warning(f"Possible block/captcha detected on {url}")
            return [], [], True

        soup = BeautifulSoup(html, "html.parser")

        # Mailto/Tel links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                mail = href.split("mailto:")[1].split("?")[0].strip()
                if mail:
                    emails.add(mail)
            elif href.startswith("tel:"):
                tel = href.split("tel:")[1].split("?")[0].strip()
                if tel:
                    phones.add(tel)

        # Free text pattern scan
        text = soup.get_text(" ", strip=True)
        for e in re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
            e = e.strip()
            if len(e) >= 6 and not e.lower().endswith(("@example.com", "@test.com", "@email.com")):
                emails.add(e)

        for p in re.findall(r"\+?\d[\d\-\s().]{6,}\d", text):
            p = p.strip()
            digits = re.sub(r"\D", "", p)
            if len(digits) >= 8:
                phones.add(p)

    except Exception as e:
        logging.warning(f"Contact extraction failed for {url}: {e}")
        return [], [], False

    return list(emails), list(phones), blocked

def discover_contact_like_pages(base_site: str) -> list[str]:
    """Seed with common paths + any nav links containing 'contact'/'about'."""
    if not base_site:
        return []
    candidates = {
        base_site,
        urljoin(base_site, "/contact"),
        urljoin(base_site, "/contact-us"),
        urljoin(base_site, "/about"),
        urljoin(base_site, "/about-us"),
        urljoin(base_site, "/support"),
        urljoin(base_site, "/customer-care"),
    }
    # Try to discover in-page nav links
    try:
        resp = SESSION.get(base_site, timeout=15)
        if resp and resp.status_code < 400 and not page_has_block(resp.text):
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                txt = (a.get_text() or "").strip().lower()
                if any(k in txt for k in ("contact", "support", "about")):
                    href = a["href"]
                    if href.startswith("http"):
                        candidates.add(href)
                    else:
                        candidates.add(urljoin(base_site, href))
    except Exception as e:
        logging.debug(f"Nav discovery failed on {base_site}: {e}")
    return list(candidates)

def get_full_contacts_for_site(base_site: str) -> tuple[list[str], list[str], bool]:
    """Crawl a few likely pages; returns (emails, phones, blocked_detected_any)."""
    all_emails, all_phones = set(), set()
    blocked_any = False
    for page in discover_contact_like_pages(base_site):
        emails, phones, blocked = extract_contacts_from_page(page)
        if blocked:
            blocked_any = True
        for e in emails:
            all_emails.add(e)
        for p in phones:
            all_phones.add(p)
        polite_sleep()
    return list(all_emails), list(all_phones), blocked_any

# -----------------
# State Management
# -----------------
def init_state():
    if "running" not in st.session_state:
        st.session_state.running = False
    if "stop_requested" not in st.session_state:
        st.session_state.stop_requested = False
    if "df_source" not in st.session_state:
        st.session_state.df_source = None
    if "col_name" not in st.session_state:
        st.session_state.col_name = None
    if "results" not in st.session_state:
        st.session_state.results = None
    if "i" not in st.session_state:
        st.session_state.i = 0
    if "block_streak" not in st.session_state:
        st.session_state.block_streak = 0
    if "checkpoint_bytes" not in st.session_state:
        st.session_state.checkpoint_bytes = None
    if "last_checkpoint_row" not in st.session_state:
        st.session_state.last_checkpoint_row = -1

def start_run():
    st.session_state.running = True
    st.session_state.stop_requested = False
    st.session_state.block_streak = 0
    st.session_state.i = 0
    # Prepare results df
    base = st.session_state.df_source.copy()
    for col in ["Website", "Emails", "Phones", "Status"]:
        if col not in base.columns:
            base[col] = ""
    st.session_state.results = base

def stop_run():
    st.session_state.stop_requested = True
    st.session_state.running = False

def reset_all():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_state()

def safe_rerun():
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()

# -----------
# UI — Header
# -----------
init_state()

st.title("📞 Contact Scraper — Minimal & Robust")
mode_text = "Search: **SerpAPI**" if serpapi_key() else "Search: **DuckDuckGo (fallback)**"
st.caption(f"{mode_text} • Balanced delays • Auto-checkpoint • Stop anytime")

# --------------
# UI — Controls
# --------------
uploaded_file = st.file_uploader("Upload Excel (.xlsx) with a column of company names", type=["xlsx"])

if uploaded_file is not None and st.session_state.df_source is None:
    try:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        if df.empty:
            st.error("Uploaded file is empty.")
        else:
            st.session_state.df_source = df
    except Exception as e:
        st.error(f"Failed to read Excel: {e}")

if st.session_state.df_source is not None and st.session_state.col_name is None:
    st.session_state.col_name = st.selectbox("Select the column containing company names:", st.session_state.df_source.columns)

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    if st.button("▶ Start", type="primary", disabled=st.session_state.running or st.session_state.df_source is None or st.session_state.col_name is None):
        start_run()
        safe_rerun()
with col2:
    if st.button("🛑 Stop", disabled=not st.session_state.running):
        stop_run()
        safe_rerun()
with col3:
    if st.button("↺ Reset"):
        reset_all()
        safe_rerun()

st.markdown("---")

# -----------------
# Main Run — Chunked
# -----------------
if st.session_state.results is not None:
    total = len(st.session_state.results)
    i = st.session_state.i

    # Progress + status
    progress = st.progress(int(i / total * 100) if total else 0)
    status_box = st.empty()
    table_placeholder = st.empty()
    download_placeholder = st.empty()
    alert_placeholder = st.empty()

    # Show current table occasionally to limit redraw cost
    if i == 0 or i % TABLE_REFRESH_EVERY == 0 or i >= total:
        table_placeholder.dataframe(st.session_state.results, use_container_width=True, height=420)

    # Always allow downloading the last checkpoint/partial if available
    if st.session_state.checkpoint_bytes is not None:
        download_placeholder.download_button(
            "📥 Download Partial (checkpoint)",
            data=st.session_state.checkpoint_bytes,
            file_name="contacts_partial_checkpoint.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="partial_dl",
        )

    # RUN LOOP — process a small chunk then yield (so STOP can take effect)
    if st.session_state.running and not st.session_state.stop_requested and i < total:
        rows_this_run = 0
        while rows_this_run < CHUNK_SIZE and st.session_state.i < total and not st.session_state.stop_requested:
            idx = st.session_state.i
            company = st.session_state.results.at[idx, st.session_state.col_name]
            display_company = str(company) if pd.notna(company) else "<EMPTY>"
            status_box.info(f"🔎 {idx+1}/{total} — {display_company}")

            # Default row outcome
            site, emails_text, phones_text, row_status = "Not Found", "Not Found", "Not Found", "Pending"

            try:
                # Validate company cell
                if not (isinstance(company, str) and company.strip()):
                    site, emails_text, phones_text, row_status = "Not Provided", "Not Found", "Not Found", "Skipped"
                else:
                    search_results = get_company_search_results(company.strip(), max_results=5)

                    chosen_base = None
                    for url in search_results:
                        base = get_base_url(url)
                        if not base:
                            continue
                        parsed = urlparse(base)
                        if is_blacklisted_domain(parsed.netloc):
                            continue
                        chosen_base = base
                        break

                    if not chosen_base:
                        row_status = "Site Not Found"
                        st.session_state.block_streak = 0  # not a block, just not found
                    else:
                        emails, phones, blocked = get_full_contacts_for_site(chosen_base)
                        site = chosen_base
                        emails_text = ", ".join(sorted(set(emails))) if emails else "Not Found"
                        phones_text = ", ".join(sorted(set(phones))) if phones else "Not Found"
                        row_status = "OK" if (emails or phones) else "No Contacts"

                        if blocked:
                            st.session_state.block_streak += 1
                        else:
                            st.session_state.block_streak = 0

            except Exception as e:
                logging.error(f"Error scraping '{display_company}': {e}")
                site, emails_text, phones_text, row_status = "Error", "Error", "Error", "Error"
                # Don't increment block streak here — it's a general error

            # Update row
            st.session_state.results.at[idx, "Website"] = site
            st.session_state.results.at[idx, "Emails"] = emails_text
            st.session_state.results.at[idx, "Phones"] = phones_text
            st.session_state.results.at[idx, "Status"] = row_status

            # Update UI occasionally
            if idx % TABLE_REFRESH_EVERY == 0 or idx == total - 1:
                table_placeholder.dataframe(st.session_state.results, use_container_width=True, height=420)

            # Save checkpoint to bytes and disk
            try:
                bytes_xlsx = to_excel_bytes(st.session_state.results)
                st.session_state.checkpoint_bytes = bytes_xlsx
                st.session_state.last_checkpoint_row = idx
                with open("latest_checkpoint.xlsx", "wb") as f:
                    f.write(bytes_xlsx)
            except Exception as e:
                logging.warning(f"Failed to write checkpoint: {e}")

            # Show warning and pause if repeated blocks detected
            if st.session_state.block_streak >= CONSEC_BLOCK_THRESHOLD:
                alert_placeholder.warning(
                    "⚠️ Multiple block/captcha detections. "
                    "Please press **STOP** and download the partial results. "
                    "You may resume later or try again after some time."
                )
                # Soft pause to be safe
                pause_for = random.randint(BATCH_PAUSE_MIN, BATCH_PAUSE_MAX)
                for rem in range(pause_for, 0, -1):
                    status_box.info(f"⏳ Cooling down due to blocks… resuming in {rem}s (you can STOP anytime).")
                    time.sleep(1)
                # After cool-down, keep going but reset streak
                st.session_state.block_streak = 0

            # Progress & pacing
            st.session_state.i += 1
            progress.progress(int(st.session_state.i / total * 100))
            polite_sleep()

            # Batch pause every BATCH_SIZE
            if st.session_state.i % BATCH_SIZE == 0 and st.session_state.i < total:
                pause_seconds = random.randint(BATCH_PAUSE_MIN, BATCH_PAUSE_MAX)
                for rem in range(pause_seconds, 0, -1):
                    status_box.info(f"🛡️ Batch pause to avoid blocking… resuming in {rem}s")
                    time.sleep(1)

            rows_this_run += 1

        # Yield control so button clicks (STOP) take effect quickly
        if st.session_state.i < total and not st.session_state.stop_requested:
            safe_rerun()

    # Finished / Stopped — present final downloads
    if st.session_state.i >= total or st.session_state.stop_requested:
        st.success("✅ Scraping completed!" if st.session_state.i >= total else "⏹️ Scraping stopped by user.")
        final_bytes = to_excel_bytes(st.session_state.results)
        final_name = f"{st.session_state.col_name}_contacts_scraped.xlsx"
        st.download_button(
            "📥 Download Excel (final/partial)",
            data=final_bytes,
            file_name=final_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="final_dl_btn",
        )
        # Also show checkpoint info
        if st.session_state.last_checkpoint_row != -1:
            st.caption(f"Checkpoint saved at row: {st.session_state.last_checkpoint_row + 1}")

else:
    st.info("Upload your Excel file to begin.")
