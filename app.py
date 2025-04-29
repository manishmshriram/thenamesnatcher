import streamlit as st
import pandas as pd
import re
import time
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from io import BytesIO

# ——— Page config & custom CSS ———
st.set_page_config(page_title="Company Contact Scraper", page_icon="📞", layout="wide")
st.markdown("""
    <style>
      .css-18e3th9 {  /* main background */
        background-color: #f5f5f5;
      }
      .stButton>button {  /* green buttons */
        background-color: #28a745;
        color: white;
        border-radius: 8px;
        padding: 0.6em 1.2em;
      }
      .stProgress > div > div > div > div {
        background-color: #28a745;
      }
    </style>
""", unsafe_allow_html=True)

st.title("📞 Company Contact Scraper")
st.write("Upload an Excel file with company names, and I'll fetch sites, emails & phones—slow but accurate scraping! 🙌")

# ——— Helper functions (using original accurate versions) ———
def get_company_website(company_name):
    query = f"{company_name} official site"
    try:
        for url in search(query, num=1, stop=1, pause=2):  # Using original parameters
            return url
    except Exception as e:
        st.warning(f"Search error for '{company_name}': {e}")
        return None

def extract_contacts(url):
    emails, phones = set(), set()
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)  # Increased timeout
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()
            # Original regex patterns that worked well
            emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text))
            phones = set(re.findall(r'\+?\d{1,4}?[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}', text))
    except Exception as e:
        st.warning(f"Error scraping {url}: {e}")
    return list(emails), list(phones)

def convert_df(df):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return buffer

# ——— File upload & processing ———
uploaded = st.file_uploader("📂 Upload your Excel (.xlsx)", type="xlsx")

if uploaded:
    try:
        df = pd.read_excel(uploaded)
        if len(df) > 1000:
            st.warning("Warning: Processing more than 1000 companies may take several hours.")
        
        # Initialize columns if they don't exist
        if 'Website' not in df.columns:
            df['Website'] = ''
        if 'Emails' not in df.columns:
            df['Emails'] = ''
        if 'Phones' not in df.columns:
            df['Phones'] = ''
        
        company_column = df.columns[0]  # Use first column for company names
        
        # Create progress elements
        prog = st.progress(0)
        status = st.empty()
        results_placeholder = st.empty()
        
        # Process each company
        for i, company in enumerate(df[company_column]):
            status.markdown(f"**Processing {i+1}/{len(df)}:** {company}")
            
            # Get website with retry logic
            website = None
            for attempt in range(3):  # Try 3 times
                website = get_company_website(company)
                if website:
                    break
                time.sleep(2)  # Wait before retry
            
            df.at[i, 'Website'] = website if website else 'Not Found'
            
            # Extract contacts if website found
            if website and website != 'Not Found':
                emails, phones = extract_contacts(website)
                df.at[i, 'Emails'] = ', '.join(emails) if emails else 'No Emails'
                df.at[i, 'Phones'] = ', '.join(phones) if phones else 'No Phones'
            
            # Update progress and display interim results
            prog.progress((i+1)/len(df))
            if (i+1) % 10 == 0 or (i+1) == len(df):  # Update display every 10 companies or at end
                results_placeholder.dataframe(df.head(50))  # Show first 50 rows
            
            # Delay to prevent blocking (longer than original for reliability)
            time.sleep(3.5)  # Increased delay for better reliability
        
        status.success("✅ Scraping complete!")
        st.balloons()
        
        # Display final results
        st.dataframe(df)
        
        # Prepare download
        output = convert_df(df)
        
        st.download_button(
            label="📥 Download Results",
            data=output,
            file_name="Company_Contacts.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Final message
        st.markdown("""
        ---
        **Download complete!**  
        This scraper prioritizes accuracy over speed.  
        For large datasets, consider running overnight.  
        """)
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        st.stop()

else:
    st.info("Please upload an Excel file (.xlsx) to begin scraping.")
