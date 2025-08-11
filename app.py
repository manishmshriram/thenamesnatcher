# ======= Team-friendly Contact Scraper for Google Colab =======
# Paste this entire cell into a new Colab notebook and run.
# Usage: Upload Excel -> select column -> Start. Click Stop to cancel. Download appears at the end.

# Install missing libs only if necessary (keeps runs fast if already installed)
import sys, subprocess, pkgutil
def pip_install(pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", *pkgs], stdout=subprocess.DEVNULL)

for pkg in ("googlesearch-python", "beautifulsoup4", "openpyxl"):
    if not pkgutil.find_loader(pkg.split("-")[0]):  # crude check
        try:
            pip_install([pkg])
        except Exception:
            pass  # if install fails, fallback code still tries duckduckgo

# --- Imports ---
from IPython.display import display, clear_output, HTML
import pandas as pd, time, re, requests, random, math
from bs4 import BeautifulSoup
from io import BytesIO
from urllib.parse import urlparse, urljoin, unquote, parse_qs

# try import googlesearch (may fail in some environments)
try:
    from googlesearch import search as google_search
except Exception:
    google_search = None

# ======= Configuration (sensible defaults, hidden from UI) =======
BATCH_PAUSE_AFTER = 40          # pause after this many search attempts
BATCH_PAUSE_MIN = 120           # pause min seconds (cooldown)
BATCH_PAUSE_MAX = 180           # pause max seconds
DELAY_MIN = 3.0                 # seconds between each company fetch (randomized)
DELAY_MAX = 7.0
DUCKDUCKGO_PAUSE = 1.0          # polite pause for DuckDuckGo query
MAX_SEARCH_RESULTS = 6

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/94.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
]

BLACKLIST = ["linkedin.", "facebook.", "twitter.", "instagram.", "youtube.", "crunchbase.",
             "glassdoor.", "yellowpages.", "yelp.", "wikipedia.", "bing.com", "google.com", "amazon."]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{6,}\d")

# ======= Small UI (upload / start / stop / progress / table) =======
upload = widgets.FileUpload(accept='.xlsx', multiple=False)
start_btn = widgets.Button(description="▶ Start Extraction", button_style="success")
stop_btn = widgets.Button(description="⏹ Stop", button_style="danger")
download_btn = widgets.Button(description="⬇️ Download (when ready)", disabled=True)
status_out = widgets.Output(layout={'border': '1px solid #ddd'})
log_out = widgets.Output(layout={'border': '1px solid #ddd', 'height': '250px', 'overflow': 'auto'})
progress_bar = widgets.IntProgress(value=0, min=0, max=100, description='Progress:', bar_style='info')
table_out = widgets.Output()

controls = widgets.HBox([start_btn, stop_btn, download_btn])
display(widgets.HTML("<h3>Company Contact Scraper — Team Edition (Colab)</h3>"))
display(upload)
display(controls)
display(progress_bar)
display(status_out)
display(table_out)
display(widgets.HTML("<b>Log</b>"))
display(log_out)

# Hide code in the notebook UI (makes it clean for team)
display(HTML('''<style>
  div.input, .prompt {display:none !important;}
</style>'''))

# ======= Globals & helpers =======
stop_flag = False
search_count = 0
_last_checkpoint_df = None
_output_filepath = "/content/Company_Contacts.xlsx"

def safe_print(msg, log=True):
    with log_out:
        print(msg)

def is_blacklisted(netloc):
    n = (netloc or "").lower()
    return any(b in n for b in BLACKLIST)

def get_base_url(url):
    try:
        p = urlparse(url)
        scheme = p.scheme or "https"
        netloc = p.netloc or urlparse("https://"+url).netloc
        if not netloc:
            return None
        return f"{scheme}://{netloc}"
    except:
        return None

# --- DuckDuckGo HTML search fallback (no JS) ---
def duckduckgo_search(query, max_results=6, pause=1.0):
    try:
        endpoint = "https://html.duckduckgo.com/html/"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        data = {"q": query}
        resp = requests.post(endpoint, data=data, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        # DuckDuckGo returns results with <a class="result__a" href="..."> or redirect like /l/?kh=-1&uddg=<url>
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http"):
                links.append(href)
            elif "uddg=" in href:
                try:
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    if "uddg" in qs:
                        decoded = unquote(qs["uddg"][0])
                        links.append(decoded)
                except:
                    continue
            if len(links) >= max_results:
                break
        time.sleep(pause)
        return links[:max_results]
    except Exception as e:
        safe_print(f"[duckduckgo_search] failed: {e}")
        return []

# --- Google search wrapper (may be blocked) ---
def google_search_candidates(query, max_results=6):
    if google_search is None:
        return []
    tries = 2
    out = []
    for attempt in range(tries):
        try:
            # google_search yields URLs; use num and stop parameters commonly supported in the package
            for u in google_search(query, num=max_results, stop=max_results, pause=2 + random.random()):
                out.append(u)
                if len(out) >= max_results:
                    break
            break
        except Exception as e:
            safe_print(f"[google_search] attempt {attempt+1} failed: {e}")
            time.sleep(1 + attempt)
    return out[:max_results]

# --- Search wrapper: try Google first, else DuckDuckGo ---
def get_search_candidates(query, max_results=6):
    # 1) Google (fast in Colab sometimes)
    candidates = google_search_candidates(query, max_results=max_results)
    if candidates:
        return candidates
    # 2) DuckDuckGo fallback
    candidates = duckduckgo_search(query, max_results=max_results, pause=DUCKDUCKGO_PAUSE)
    return candidates

# --- Contact extraction from a page ---
def extract_contacts_from_page(url):
    emails, phones = set(), set()
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r is None or r.status_code >= 400:
            return [], []
        html_lower = r.text.lower()
        for block in ("recaptcha", "unusual traffic", "please verify", "are you a robot"):
            if block in html_lower:
                safe_print(f"[extract] block/captcha detected on {url}")
                return [], []
        soup = BeautifulSoup(r.text, "html.parser")
        # mailto / tel links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                emails.add(href.split("mailto:")[1].split("?")[0].strip())
            if href.startswith("tel:"):
                phones.add(href.split("tel:")[1].split("?")[0].strip())
        # regex fallback
        text = soup.get_text(" ", strip=True)
        for e in EMAIL_RE.findall(text):
            if not e.lower().endswith(("@example.com", "@test.com", "@email.com")):
                emails.add(e)
        for p in PHONE_RE.findall(text):
            digits = re.sub(r"\D", "", p)
            if len(digits) >= 8:
                phones.add(p.strip())
    except Exception as e:
        safe_print(f"[extract_contacts_from_page] error for {url}: {e}")
    return list(emails), list(phones)

def get_contacts_for_site(base_site):
    if not base_site:
        return [], []
    candidates = [base_site]
    for path in ("/contact", "/contact-us", "/about", "/about-us", "/team", "/support"):
        candidates.append(urljoin(base_site, path))
    all_emails, all_phones = set(), set()
    for page in candidates:
        e,p = extract_contacts_from_page(page)
        for x in e: all_emails.add(x)
        for x in p: all_phones.add(x)
        time.sleep(random.uniform(0.5, 1.4))
    return list(all_emails), list(all_phones)

# ======= Core loop =======
def run_scraper(bytes_content, company_col=None):
    global stop_flag, search_count, _last_checkpoint_df
    stop_flag = False
    search_count = 0
    try:
        df = pd.read_excel(BytesIO(bytes_content), engine="openpyxl")
    except Exception as e:
        safe_print(f"[run_scraper] failed to read Excel: {e}")
        return None

    # default column = first
    if company_col is None:
        company_col = df.columns[0]

    # prepare result df
    res = df.copy()
    res["Website"] = ""
    res["Emails"] = ""
    res["Phones"] = ""
    res["Status"] = ""

    total = len(res)
    with status_out:
        clear_output(wait=True)
        print(f"Starting scraping for {total} rows using this Colab session. Please keep this tab open.")

    for i, raw_company in enumerate(res[company_col].astype(str)):
        if stop_flag:
            safe_print("Stopped by user.")
            break

        company = raw_company.strip()
        with status_out:
            clear_output(wait=True)
            print(f"[{i+1}/{total}] Searching: {company}")

        # skip empty
        if not company:
            res.at[i, "Website"] = "No Name"
            res.at[i, "Status"] = "Skipped"
            # update table
            with table_out:
                clear_output(wait=True)
                display(res.head(50))
            progress_bar.value = math.floor((i+1)/total*100)
            continue

        # Pause after batch to avoid blocks
        if search_count > 0 and search_count % BATCH_PAUSE_AFTER == 0:
            pause_for = random.randint(BATCH_PAUSE_MIN, BATCH_PAUSE_MAX)
            safe_print(f"[cooldown] {search_count} searches done — pausing {pause_for}s to avoid blocking.")
            # show countdown
            for remain in range(pause_for, 0, -1):
                with status_out:
                    clear_output(wait=True)
                    print(f"[{i+1}/{total}] Cooling down for {remain} s ...")
                time.sleep(1)
                if stop_flag:
                    break
            with status_out:
                clear_output(wait=True)
                print("Resuming...")

        # Try searching (Google then DuckDuckGo)
        chosen_site = None
        search_tries = 3
        for attempt in range(search_tries):
            if stop_flag:
                break
            q = f"{company} official website"
            candidates = get_search_candidates(q, max_results=MAX_SEARCH_RESULTS)
            search_count += 1
            # pick first non-blacklisted reachable base
            for u in candidates:
                base = get_base_url(u)
                if not base: continue
                parsed = urlparse(base)
                if is_blacklisted(parsed.netloc): 
                    continue
                # quick reachability check
                try:
                    rr = requests.get(base, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=8)
                    if rr.status_code < 400:
                        chosen_site = base
                        break
                except:
                    continue
            if chosen_site:
                break
            # if none found, tweak query slightly and retry (adds company + "head office" etc)
            time.sleep(1 + random.random())
            if attempt == 0:
                q = f"{company} head office official site"
            elif attempt == 1:
                q = f"{company} {company.split()[0]} official site"
            else:
                q = f"{company} website"
        # record
        if not chosen_site:
            res.at[i, "Website"] = "Not Found"
            res.at[i, "Status"] = "Site Not Found"
        else:
            res.at[i, "Website"] = chosen_site
            # extract contacts
            emails, phones = get_contacts_for_site(chosen_site)
            res.at[i, "Emails"] = ", ".join(emails) if emails else "Not Found"
            res.at[i, "Phones"] = ", ".join(phones) if phones else "Not Found"
            res.at[i, "Status"] = "OK" if (emails or phones) else "No Contacts"

        # periodic UI updates
        if i % 1 == 0 or i == total-1:
            with table_out:
                clear_output(wait=True)
                display(res.head(100))  # show the top 100 rows for preview
        progress_bar.value = math.floor((i+1)/total*100)

        # checkpoint save every 10 rows
        if i % 10 == 0 or i == total-1:
            try:
                res.to_excel(_output_filepath, index=False)
                _last_checkpoint_df = res.copy()
            except Exception as e:
                safe_print(f"[checkpoint] failed save: {e}")

        # patient/random delay between companies
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # final save
    try:
        res.to_excel(_output_filepath, index=False)
        safe_print(f"Saved final results to {_output_filepath}")
    except Exception as e:
        safe_print(f"Final save error: {e}")

    return res

# ======= Button callbacks =======
uploaded_bytes = None
def on_upload_change(change):
    global uploaded_bytes
    uploaded_bytes = None
    if upload.value:
        # get uploaded file bytes
        key = list(upload.value.keys())[0]
        uploaded_bytes = upload.value[key]['content']
        with status_out:
            clear_output(wait=True)
            print(f"Uploaded: {key} — size {len(uploaded_bytes)//1024} KB")
    else:
        with status_out:
            clear_output(wait=True)
            print("No file uploaded.")

def on_start_clicked(b):
    global uploaded_bytes, stop_flag
    if not upload.value:
        with status_out:
            clear_output(wait=True)
            print("Please upload an Excel (.xlsx) file first.")
        return
    # simple UI for choosing column (if multiple)
    try:
        df_preview = pd.read_excel(BytesIO(uploaded_bytes), engine="openpyxl")
    except Exception as e:
        with status_out:
            clear_output(wait=True)
            print(f"Failed reading uploaded file: {e}")
        return
    cols = list(df_preview.columns)
    if len(cols) == 0:
        with status_out:
            clear_output(wait=True)
            print("Uploaded file has no columns.")
        return

    # pick column (simple single-option dialog)
    col_selector = widgets.Dropdown(options=cols, description="Company column:")
    ok_btn = widgets.Button(description="OK", button_style="success")
    cancel_btn = widgets.Button(description="Cancel", button_style="warning")
    selector_out = widgets.Output()

    def on_ok(c):
        selector_out.clear_output()
        with selector_out:
            print("Starting... (this cell will show live progress)")
        start_btn.disabled = True
        stop_btn.disabled = False
        # run scraper in blocking fashion (Colab will execute here)
        res = run_scraper(uploaded_bytes, company_col=col_selector.value)
        start_btn.disabled = False
        stop_btn.disabled = True
        if res is not None:
            download_btn.disabled = False
            with status_out:
                clear_output(wait=True)
                print("Scraping completed. Use Download button to get the file.")
        else:
            with status_out:
                clear_output(wait=True)
                print("Scraping ended with errors; check logs for hints.")

    def on_cancel(c):
        selector_out.clear_output()
        with status_out:
            clear_output(wait=True)
            print("Cancelled start.")

    ok_btn.on_click(on_ok)
    cancel_btn.on_click(on_cancel)
    with status_out:
        clear_output(wait=True)
        display(widgets.HBox([col_selector, ok_btn, cancel_btn]), selector_out)

def on_stop_clicked(b):
    global stop_flag
    stop_flag = True
    with status_out:
        clear_output(wait=True)
        print("Stop requested — will halt after current request completes.")

def on_download_clicked(b):
    try:
        files.download(_output_filepath)
    except Exception as e:
        safe_print(f"Download failed: {e}")

# bind
upload.observe(on_upload_change, names='value')
start_btn.on_click(on_start_clicked)
stop_btn.on_click(on_stop_clicked)
download_btn.on_click(on_download_clicked)

# initial hints
with status_out:
    clear_output(wait=True)
    print("Upload an Excel (.xlsx) file and press Start. Each team member should run their own Colab session.")
with log_out:
    clear_output(wait=True)
    print("Log starts here. Errors & important notices will appear in this box.")
