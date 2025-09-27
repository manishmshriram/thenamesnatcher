import streamlit as st
import pandas as pd
import requests
import time
import tldextract

# Common domain TLDs to test
COMMON_TLDS = ['.com', '.net', '.org', '.co', '.io', '.biz', '.info',
               '.us', '.uk', '.de', '.in', '.cn', '.com.au', '.ca',
               '.fr', '.jp', '.ru', '.br', '.za', '.nl', '.se']

# Optional country code mapping from TLD for known CC
CC_TLD_MAP = {
    'us': 'United States', 'uk': 'United Kingdom', 'de': 'Germany', 'in': 'India',
    'cn': 'China', 'au': 'Australia', 'ca': 'Canada', 'fr': 'France', 'jp': 'Japan',
    'ru': 'Russia', 'br': 'Brazil', 'za': 'South Africa', 'nl': 'Netherlands',
    'se': 'Sweden'
}

def guess_domains(company_name):
    """Generate domain guesses from company name."""
    company = company_name.lower().replace(' ', '').replace(',', '').replace('.', '')
    domains = []
    for tld in COMMON_TLDS:
        domains.append(f"https://{company}{tld}")
    return domains

def check_domain_exists(url):
    """Check if domain is reachable (status 200-399 from HEAD or GET)."""
    try:
        resp = requests.head(url, timeout=5, allow_redirects=True)
        if resp.status_code >= 200 and resp.status_code < 400:
            return True
        else:
            # Sometimes head is blocked, try get
            resp = requests.get(url, timeout=5)
            return resp.status_code >= 200 and resp.status_code < 400
    except:
        return False

def domain_to_country(domain):
    """Infer country from domain TLD if possible"""
    ext = tldextract.extract(domain)
    tld = ext.suffix.lower()
    # Try to get country code from suffix for ccTLDs (like .in, .uk)
    parts = tld.split('.')
    if len(parts) == 1 and parts[0] in CC_TLD_MAP:
        return CC_TLD_MAP[parts[0]]
    elif len(parts) == 2 and parts[1] in CC_TLD_MAP:
        return CC_TLD_MAP[parts[1]]
    else:
        return ''

def process_companies(df):
    results = []
    for idx, row in df.iterrows():
        company = str(row['Company'])
        country_col = str(row['Country']) if 'Country' in row else ''
        domains = guess_domains(company)
        website_found = ''
        domain_country = ''
        for d in domains:
            if check_domain_exists(d):
                website_found = d
                domain_country = domain_to_country(d)
                break
            time.sleep(0.5)  # polite delay
        results.append({
            'Company': company,
            'Provided Country': country_col,
            'Website Found': website_found,
            'Country from Domain': domain_country
        })
    return pd.DataFrame(results)

# Streamlit app
st.title("Company Website & Country Pre-Validator")

uploaded_file = st.file_uploader("Upload Excel or CSV file with 'Company' and optional 'Country' columns", type=['xlsx', 'csv'])

if uploaded_file:
    if uploaded_file.name.endswith('csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.write(f"Preview of your data ({len(df)} rows):")
    st.dataframe(df.head())

    if st.button("Run Validation"):
        with st.spinner('Validating domains and detecting countries... This may take some time'):
            result_df = process_companies(df)
        st.success('Validation Complete!')
        st.dataframe(result_df)
        st.download_button("Download Results as CSV", result_df.to_csv(index=False), "company_validation_results.csv")
