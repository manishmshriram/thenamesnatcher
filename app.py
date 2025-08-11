import streamlit as st
import pandas as pd
import re
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import time
import random
import logging
from io import BytesIO
from urllib.parse import urlparse, urljoin
import os

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Streamlit Page Config ---
st.set_page_config(page_title="Contact Scraper", layout="centered")
st.title("📞 Company Contact Scraper")
st.write("Upload an Excel file and select the column containing company names.")

uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

# --- Sidebar controls for throttling / pause behavior ---
st.sidebar.header("Scraping Controls")
batch_size = st.sidebar.number_input("Stop after this many searches (batch size)", min_value=10, max_value=200, value=40, step=10)
pause_min = st.sidebar.number_input("Pause min seconds after each batch", min_value=30, max_value=1200, value=180, step=10)
pause_max = st.sidebar.number_input("Pause max seconds after each batch", min_value=60, max_value=1800, value=300, step=10)
delay_min = st.sidebar.number_input("Delay min (sec) between single requests", min_value=1, max_value=30, value=3, step=1)
delay_max = st.sidebar.number_input("Delay max (sec) between single requests", min_value=1, max_value=60, value=8, step=1)
search_pause = st.sidebar.slider("Pause between Google search requests (sec)", 0.5, 5.0, 1.5, 0.1)

# --- User Agent Pool (kept / expanded) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/94.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36",
    # Add more if needed
]

# --- Helpers ---
def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def retry_request(func, *args, retries=3, delay=5, **kwargs):
    """Simple retry wrapper."""
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.warning(f"Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
    return None

def clean_phone(raw):
    digits = re.sub(r"\D", "", raw)
    return digits

# --- Search + domain selection logic (more robust) ---
def get_company_website(company_name, max_results=5):
    """
    Use googlesearch.search to get top results and pick the most likely company website.
    Returns base URL (scheme + netloc) or None.
    """
    query = f"{company_name} official website"
    try:
        # try a few times to get search results (some googlesearch versions may be flaky)
        results = None
        for attempt in range(3):
            try:
                results = list(search(query, num=max_results, stop=max_results, pause=search_pause))
                if results:
                    break
            except Exception as e:
                logging.warning(f"Google search attempt {attempt+1} failed for '{company_name}': {e}")
                time.sleep(1 + attempt)
        if not results:
            return None

        # blacklist domains that are unlikely to be the official site
        blacklist = ["linkedin.", "facebook.", "twitter.", "instagram.", "youtube.", "crunchbase.", "zoominfo.",
                     "glassdoor.", "yellowpages.", "yelp.", "wikipedia.", "bing.com", "google.com", "amazon."]
        for url in results:
            try:
                parsed = urlparse(url)
                netloc = parsed.netloc.lower()
                if any(b in netloc for b in blacklist):
                    continue
                if parsed.scheme not in ("http", "https"):
                    continue
                base = f"{parsed.scheme}://{parsed.netloc}"
                logging.info(f"Selected website for '{company_name}': {base}")
                return base
            except Exception:
                continue

        # fallback: return first result's base URL if nothing else
        parsed = urlparse(results[0])
        if parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else f"https://{parsed.netloc}"
    except Exception as e:
        logging.warning(f"Website retrieval error for '{company_name}': {e}")
    return None

# --- Contact extraction from a single page (robust with headers & timeout) ---
def extract_contacts_from_page(url):
    emails, phones = set(), set()
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"}
    try:
        resp = retry_request(requests.get, url, headers=headers, timeout=12, retries=2, delay=3)
        if resp is None:
            logging.warning(f"No response for {url}")
            return [], []
        if resp.status_code >= 400:
            logging.warning(f"Bad status {resp.status_code} for {url}")
            return [], []

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        # emails
        found_emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
        # phones — allow +country and common separators
        found_phones = set(re.findall(r"\+?\d[\d\-\s().]{6,}\d", text))

        # Filter emails
        filtered_emails = set()
        for e in found_emails:
            if e.lower().endswith(("@example.com", "@test.com", "@email.com")):
                continue
            # minimal length to avoid nonsense
            if len(e) < 6:
                continue
            filtered_emails.add(e)

        # Filter phones: keep those with at least 8 digits
        filtered_phones = set()
        for p in found_phones:
            d = clean_phone(p)
            if len(d) >= 8:
                # keep original formatting but ensure it's not a pure long numeric ID (heuristic)
                filtered_phones.add(p.strip())

        emails.update(filtered_emails)
        phones.update(filtered_phones)

    except Exception as e:
        logging.warning(f"Error extracting {url}: {e}")

    return list(emails), list(phones)

# --- Try main site and common contact pages ---
def get_full_contacts_for_site(base_site):
    all_emails, all_phones = set(), set()
    if not base_site:
        return [], []
    # candidate pages: base + common contact/about pages
    candidates = [base_site]
    for path in ("/contact", "/contact-us", "/about", "/about-us", "/team", "/support", "/customer-care"):
        candidates.append(urljoin(base_site, path))

    # sometimes the /contact page is located under different URL structures, but the above covers common cases
    for page in candidates:
        try:
            emails, phones = extract_contacts_from_page(page)
            all_emails.update(emails)
            all_phones.update(phones)
        except Exception as e:
            logging.warning(f"Failed to scrape page {page}: {e}")

    return list(all_emails), list(all_phones)

# --- Main App Logic ---
if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        if df.empty:
            st.error("Uploaded file is empty.")
        else:
            col_option = st.selectbox("Select the column with company names:", df.columns)

            if st.button("Start Scraping"):
                # Prepare results DataFrame (preserve original columns)
                result_df = df.copy()
                # add / reset columns
                result_df["Website"] = ""
                result_df["Emails"] = ""
                result_df["Phones"] = ""
                result_df["Status"] = ""

                total = len(result_df)
                progress = st.progress(0)
                status = st.empty()
                # placeholder to show live-updating table
                table_placeholder = st.empty()

                # periodic checkpoint download button (user can download partial results anytime)
                checkpoint_bytes = None
                last_checkpoint_i = -1

                for i, company in enumerate(result_df[col_option]):
                    # show status
                    display_company = company if pd.notna(company) else "<EMPTY>"
                    status.text(f"🔎 {i+1}/{total}: {display_company}")
                    logging.info(f"Processing [{i+1}/{total}]: {display_company}")

                    # skip empty company names
                    if not (isinstance(company, str) and company.strip()):
                        result_df.at[i, "Website"] = "Not Provided"
                        result_df.at[i, "Emails"] = "Not Found"
                        result_df.at[i, "Phones"] = "Not Found"
                        result_df.at[i, "Status"] = "Skipped"
                        # update table and progress
                        if (i % 5) == 0:  # update intermittently for performance
                            table_placeholder.dataframe(result_df)
                        progress.progress(int((i + 1) / total * 100))
                        continue

                    try:
                        website = get_company_website(company.strip())
                        if website:
                            emails, phones = get_full_contacts_for_site(website)
                            result_df.at[i, "Website"] = website
                            result_df.at[i, "Emails"] = ", ".join(emails) if emails else "Not Found"
                            result_df.at[i, "Phones"] = ", ".join(phones) if phones else "Not Found"
                            result_df.at[i, "Status"] = "OK" if (emails or phones) else "No Contacts"
                        else:
                            logging.info(f"Website not found for '{company}'")
                            result_df.at[i, "Website"] = "Not Found"
                            result_df.at[i, "Emails"] = "Not Found"
                            result_df.at[i, "Phones"] = "Not Found"
                            result_df.at[i, "Status"] = "Site Not Found"
                    except Exception as e:
                        logging.error(f"Error scraping {company}: {e}")
                        result_df.at[i, "Website"] = "Error"
                        result_df.at[i, "Emails"] = "Error"
                        result_df.at[i, "Phones"] = "Error"
                        result_df.at[i, "Status"] = "Error"

                    # update table periodically to avoid too many UI redraws
                    if (i % 3) == 0 or i == total - 1:
                        table_placeholder.dataframe(result_df)

                    # update progress
                    progress.progress(int((i + 1) / total * 100))

                    # Save checkpoint every 10 rows or at the end (so user can download partial results)
                    if (i % 10) == 0 or i == total - 1:
                        checkpoint_bytes = to_excel_bytes(result_df)
                        last_checkpoint_i = i

                    # Respect per-request delay to reduce blocking
                    sleep_time = random.uniform(delay_min, delay_max)
                    logging.info(f"Sleeping {sleep_time:.1f}s between requests.")
                    time.sleep(sleep_time)

                    # If we hit a batch boundary, pause for a considerable time to avoid Google blocking
                    if (i + 1) % batch_size == 0 and (i + 1) < total:
                        pause_seconds = random.randint(int(pause_min), int(pause_max))
                        msg = f"⚠️ Completed {i+1} searches — pausing for {pause_seconds} seconds to avoid blocking by Google..."
                        logging.info(msg)
                        status.text(msg)
                        # keep updating the table during long pause so user sees current progress
                        table_placeholder.dataframe(result_df)
                        # Sleep in smaller increments to keep server responsive to interrupts (and update UI)
                        gran = 10
                        for _ in range(int(pause_seconds / gran)):
                            time.sleep(gran)
                        remaining = pause_seconds % gran
                        if remaining:
                            time.sleep(remaining)
                        status.text("🔁 Resuming scraping...")

                # Final UI updates
                status.text("✅ Scraping completed!")
                table_placeholder.dataframe(result_df)
                progress.progress(100)

                # final Excel bytes
                final_bytes = to_excel_bytes(result_df)
                file_name = f"{col_option}_contacts_scraped.xlsx"

                st.success("✅ Ready for download!")
                st.download_button(
                    label="📥 Download Excel (final)",
                    data=final_bytes,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="final_download",
                )

                # If a checkpoint exists, allow user to download it too
                if checkpoint_bytes is not None and last_checkpoint_i != -1:
                    st.info(f"Checkpoint saved at row: {last_checkpoint_i+1}")
                    st.download_button(
                        label="📥 Download Last Checkpoint (partial)",
                        data=checkpoint_bytes,
                        file_name=f"{col_option}_contacts_checkpoint_row_{last_checkpoint_i+1}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="checkpoint_download",
                    )

    except Exception as e:
        logging.error(f"Unexpected error during scraping: {e}")
        st.error(f"❌ Unexpected error: {e}")
