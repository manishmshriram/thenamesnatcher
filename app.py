# (Full script — replace your current app file with this)
import streamlit as st
import pandas as pd
import re
import requests
from bs4 import BeautifulSoup
import time
import random
import logging
from io import BytesIO
from urllib.parse import urlparse, urljoin, unquote, parse_qs

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Streamlit UI ---
st.set_page_config(page_title="Contact Scraper (Robust)", layout="centered")
st.title("📞 Company Contact Scraper — Robust & Patient")
st.write("This version prefers accuracy over speed. Use SerpAPI (recommended) or the free DuckDuckGo fallback.")

# --- Sidebar settings ---
st.sidebar.header("Search & Throttling Settings")
mode = st.sidebar.selectbox("Search mode", ["DuckDuckGo (free)", "SerpAPI (recommended)"])
serpapi_key = st.sidebar.text_input("SerpAPI API key (optional)", type="password")
batch_size = st.sidebar.number_input("Stop after this many searches (batch size)", min_value=10, max_value=500, value=40, step=10)
pause_min = st.sidebar.number_input("Pause min seconds after each batch", min_value=15, max_value=3600, value=180, step=5)
pause_max = st.sidebar.number_input("Pause max seconds after each batch", min_value=30, max_value=7200, value=300, step=5)
delay_min = st.sidebar.number_input("Delay min (sec) between single requests", min_value=0.5, max_value=60.0, value=3.0, step=0.1, format="%.1f")
delay_max = st.sidebar.number_input("Delay max (sec) between single requests", min_value=0.5, max_value=120.0, value=6.0, step=0.1, format="%.1f")
search_pause = st.sidebar.slider("DuckDuckGo search pause (sec)", 0.1, 5.0, 1.0, 0.1)
num_search_results = st.sidebar.number_input("Number of search results to consider", min_value=1, max_value=10, value=5, step=1)

st.sidebar.markdown("---")
st.sidebar.write("Tip: For best results use SerpAPI and provide an API key. Otherwise the DuckDuckGo fallback will be used (free).")

uploaded_file = st.file_uploader("Upload Excel (.xlsx) with company names", type=["xlsx"])

# --- User-Agent pool (expanded) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/94.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36",
]

# --- Helpers ---
def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def clean_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw)

def is_blacklisted_domain(netloc: str) -> bool:
    blacklist = ["linkedin.", "facebook.", "twitter.", "instagram.", "youtube.", "crunchbase.",
                 "zoominfo.", "glassdoor.", "yellowpages.", "yelp.", "wikipedia.", "bing.com", "google.com", "amazon."]
    netloc = netloc.lower()
    return any(b in netloc for b in blacklist)

def get_base_url(url: str) -> str:
    try:
        p = urlparse(url)
        if not p.scheme:
            scheme = "https"
        else:
            scheme = p.scheme
        if not p.netloc:
            parsed = urlparse("https://" + url)
            if not parsed.netloc:
                return None
            return f"https://{parsed.netloc}"
        return f"{scheme}://{p.netloc}"
    except Exception:
        return None

# --- Search implementations ---
def search_with_serpapi(query: str, api_key: str, num_results: int = 5):
    """Use SerpAPI (requires API key). Returns list of urls."""
    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": num_results,
        }
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        urls = []
        for r in data.get("organic_results", [])[:num_results]:
            link = r.get("link") or r.get("url")
            if link:
                urls.append(link)
        for k in ("top_results", "related_questions"):
            for item in data.get(k, [])[:num_results]:
                link = item.get("link") or item.get("url")
                if link:
                    urls.append(link)
        seen = set()
        out = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out[:num_results]
    except Exception as e:
        logging.warning(f"SerpAPI search failed: {e}")
        return []

def search_with_duckduckgo_html(query: str, num_results: int = 5, pause: float = 1.0):
    """Simple DuckDuckGo HTML search fallback (no JS). Returns list of urls."""
    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        data = {"q": query}
        resp = requests.post(url, data=data, headers=headers, timeout=15)
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
        out = []
        seen = set()
        for u in links:
            if u not in seen:
                seen.add(u)
                out.append(u)
            if len(out) >= num_results:
                break
        time.sleep(pause)
        return out
    except Exception as e:
        logging.warning(f"DuckDuckGo search failed: {e}")
        return []

def get_company_search_results(company_name: str, max_results: int = 5):
    """Wrapper that uses SerpAPI if key provided and mode set, otherwise DuckDuckGo fallback."""
    query = f"{company_name} official website"
    if mode == "SerpAPI (recommended)" and serpapi_key:
        return search_with_serpapi(query, serpapi_key, num_results=max_results)
    else:
        return search_with_duckduckgo_html(query, num_results=max_results, pause=search_pause)

# --- Contact extraction ---
def extract_contacts_from_page(url: str):
    emails = set()
    phones = set()
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"}
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp is None or resp.status_code >= 400:
            return [], []
        html = resp.text
        block_signs = ["unusual traffic", "recaptcha", "are you a robot", "please verify you're a human"]
        low = html.lower()
        for s in block_signs:
            if s in low:
                logging.warning(f"Possible block/captcha detected on {url}")
                return [], []
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                mail = href.split("mailto:")[1].split("?")[0]
                emails.add(mail.strip())
            if href.startswith("tel:"):
                tel = href.split("tel:")[1].split("?")[0]
                phones.add(tel.strip())
        text = soup.get_text(" ", strip=True)
        found_emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
        for e in found_emails:
            if len(e) >= 6 and not e.lower().endswith(("@example.com", "@test.com", "@email.com")):
                emails.add(e)
        found_phones = set(re.findall(r"\+?\d[\d\-\s().]{6,}\d", text))
        for p in found_phones:
            digits = re.sub(r"\D", "", p)
            if len(digits) >= 8:
                phones.add(p.strip())
    except Exception as e:
        logging.warning(f"Contact extraction failed for {url}: {e}")
        return [], []
    return list(emails), list(phones)

def get_full_contacts_for_site(base_site: str):
    all_emails = set()
    all_phones = set()
    if not base_site:
        return [], []
    candidates = [base_site]
    for path in ("/contact", "/contact-us", "/about", "/about-us", "/team", "/support", "/customer-care"):
        candidates.append(urljoin(base_site, path))
    for page in candidates:
        try:
            emails, phones = extract_contacts_from_page(page)
            for e in emails:
                all_emails.add(e)
            for p in phones:
                all_phones.add(p)
            time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            logging.warning(f"Failed to fetch {page}: {e}")
    return list(all_emails), list(all_phones)

# --- Main scraping loop ---
if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        if df.empty:
            st.error("Uploaded file is empty.")
        else:
            col_option = st.selectbox("Select the column with company names:", df.columns)

            if st.button("Start Scraping"):
                result_df = df.copy()
                result_df["Website"] = ""
                result_df["Emails"] = ""
                result_df["Phones"] = ""
                result_df["Status"] = ""

                total = len(result_df)
                progress = st.progress(0)
                status = st.empty()
                table_placeholder = st.empty()

                checkpoint_bytes = None
                last_checkpoint_i = -1

                for i, company in enumerate(result_df[col_option]):
                    display_company = company if pd.notna(company) else "<EMPTY>"
                    status.text(f"🔎 {i+1}/{total}: {display_company}")
                    logging.info(f"Processing [{i+1}/{total}]: {display_company}")

                    if not (isinstance(company, str) and company.strip()):
                        result_df.at[i, "Website"] = "Not Provided"
                        result_df.at[i, "Emails"] = "Not Found"
                        result_df.at[i, "Phones"] = "Not Found"
                        result_df.at[i, "Status"] = "Skipped"
                        if (i % 5) == 0:
                            table_placeholder.dataframe(result_df)
                        progress.progress(int((i + 1) / total * 100))
                        continue

                    try:
                        search_results = get_company_search_results(company.strip(), max_results=num_search_results)

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
                            result_df.at[i, "Website"] = "Not Found"
                            result_df.at[i, "Emails"] = "Not Found"
                            result_df.at[i, "Phones"] = "Not Found"
                            result_df.at[i, "Status"] = "Site Not Found"
                        else:
                            emails, phones = get_full_contacts_for_site(chosen_base)
                            result_df.at[i, "Website"] = chosen_base
                            result_df.at[i, "Emails"] = ", ".join(emails) if emails else "Not Found"
                            result_df.at[i, "Phones"] = ", ".join(phones) if phones else "Not Found"
                            result_df.at[i, "Status"] = "OK" if (emails or phones) else "No Contacts"

                    except Exception as e:
                        logging.error(f"Error scraping {company}: {e}")
                        result_df.at[i, "Website"] = "Error"
                        result_df.at[i, "Emails"] = "Error"
                        result_df.at[i, "Phones"] = "Error"
                        result_df.at[i, "Status"] = "Error"

                    if (i % 2) == 0 or i == total - 1:
                        table_placeholder.dataframe(result_df)

                    progress.progress(int((i + 1) / total * 100))

                    if (i % 10) == 0 or i == total - 1:
                        checkpoint_bytes = to_excel_bytes(result_df)
                        last_checkpoint_i = i

                    time.sleep(random.uniform(delay_min, delay_max))

                    if (i + 1) % batch_size == 0 and (i + 1) < total:
                        pause_seconds = random.randint(int(pause_min), int(pause_max))
                        status.text(f"⚠️ Completed {i+1} searches — pausing for {pause_seconds} seconds to avoid blocking...")
                        logging.info(f"Pausing {pause_seconds}s after {i+1} searches.")
                        for rem in range(pause_seconds, 0, -1):
                            status.text(f"⚠️ Paused. Resuming in {rem} sec...")
                            time.sleep(1)
                        status.text("🔁 Resuming scraping...")

                status.text("✅ Scraping completed!")
                table_placeholder.dataframe(result_df)
                progress.progress(100)

                final_bytes = to_excel_bytes(result_df)
                file_name = f"{col_option}_contacts_scraped.xlsx"

                st.success("✅ Ready for download!")
                st.download_button("📥 Download Excel (final)", final_bytes, file_name,
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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
