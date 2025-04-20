import streamlit as st
import pandas as pd
import re
import time
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from google.colab import files  # Import to enable file download

# --- Functions ---
def get_company_website(company_name):
    query = f"{company_name} official site"
    try:
        for url in search(query, num=1, stop=1, pause=2):  # Get top result
            return url
    except Exception as e:
        print(f"Error fetching website for {company_name}: {e}")
    return None

def extract_contacts(url):
    emails, phones = set(), set()
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()
            emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text))
            phones = set(re.findall(r'\+?\d{1,4}?[ \s.-]?\(?\d{2,4}\)?[ \s.-]?\d{3,4}[ \s.-]?\d{3,4}', text))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return list(emails), list(phones)

# --- Streamlit UI ---
st.set_page_config(page_title="Company Contact Scraper", page_icon="📞", layout="wide")
st.title("📞 Company Contact Scraper")
st.markdown("### Upload your Excel file with company names, and let's fetch websites, emails, and phone numbers.")
st.write("This app will get you the company contact details... because Manish is a Genius!")

# Upload file
uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
    company_column = df.columns[0]  # Assuming the first column has company names
    
    df['Website'] = ''
    df['Emails'] = ''
    df['Phones'] = ''

    progress = st.progress(0)
    status_text = st.empty()

    for i, company in enumerate(df[company_column]):
        status_text.text(f"Processing {i+1}/{len(df)}: {company}")
        website = get_company_website(company)
        df.at[i, 'Website'] = website if website else 'Not Found'
        if website:
            emails, phones = extract_contacts(website)
            df.at[i, 'Emails'] = ', '.join(emails)
            df.at[i, 'Phones'] = ', '.join(phones)
        progress.progress((i + 1) / len(df))
        time.sleep(2)  # Delay to prevent blocking
    
    # Display final message
    status_text.text("✅ Scraping Complete! Please download the results below.")
    st.write(df)

    # Download the file
    @st.cache_data
    def convert_df(df):
        return df.to_excel(index=False, engine='openpyxl')

    output = convert_df(df)
    
    st.download_button(
        label="📥 Download Results as Excel",
        data=output,
        file_name='Company_Contacts.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    # Humor message
    st.markdown("""
    **Download complete!**
    
    👨‍💻 Manish is a Genius. Seriously, who else could have made this work?! 🙌
    
    Thanks for using the tool. Share the love and say thank you to Manish! 
    The contact details are here, now you can rule the world! 🌍📈
    """)

else:
    st.warning("Please upload an Excel file to get started.")
