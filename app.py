import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import urllib.parse

# Function to simulate Google Search using DuckDuckGo (to avoid blocking)
def google_search(company_name):
    query = f"{company_name} contact site:.com"
    url = f"https://duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        time.sleep(5)  # Wait after search
        soup = BeautifulSoup(res.text, "html.parser")
        links = [a['href'] for a in soup.select('.result__a') if 'http' in a['href']]
        return links
    except Exception as e:
        return []

# Function to extract emails and phone numbers
def extract_contacts(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        res = requests.get(url, headers=headers, timeout=15)
        time.sleep(5)  # Wait after page load
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text()

        emails = list(set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)))
        phones = list(set(re.findall(r"\+?\d[\d\s().-]{7,}\d", text)))

        return emails, phones
    except:
        return [], []

# Streamlit UI
st.set_page_config(page_title="The Name Snatcher", layout="centered")
st.title("🔍 The Name Snatcher")
st.markdown("Enter a **company name** and I’ll try to find their contact email and phone number. It may take 10–15 seconds. Please be patient!")

company = st.text_input("Enter Company Name", placeholder="e.g., Infosys")

if st.button("Find Contact Details"):
    if not company.strip():
        st.warning("Please enter a valid company name.")
    else:
        with st.spinner("Snatching contact info... 🕵️‍♂️ This may take a few seconds."):
            links = google_search(company)
            email_found = []
            phone_found = []

            for link in links[:3]:  # Try top 3 results only
                emails, phones = extract_contacts(link)
                if emails:
                    email_found.extend(emails)
                if phones:
                    phone_found.extend(phones)
                time.sleep(5)  # Delay between link checks

            email_found = list(set(email_found))
            phone_found = list(set(phone_found))

        if email_found or phone_found:
            st.success("Here are the contact details I found:")
            if email_found:
                st.markdown("📧 **Emails Found:**")
                for e in email_found:
                    st.code(e, language="text")
            if phone_found:
                st.markdown("📞 **Phone Numbers Found:**")
                for p in phone_found:
                    st.code(p, language="text")
        else:
            st.error("No contact details found. Try another company or check spelling.")
