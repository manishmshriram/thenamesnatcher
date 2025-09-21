from serpapi import GoogleSearch
import requests
from bs4 import BeautifulSoup
import re

SERPAPI_API_KEY = "YOUR_API_KEY_HERE"  # Replace with your actual key

def get_company_website(company_name):
    params = {
        "engine": "google",
        "q": f"{company_name} official site",
        "api_key": SERPAPI_API_KEY
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        if "organic_results" in results and results["organic_results"]:
            return results["organic_results"][0]["link"]
    except Exception as e:
        print(f"Error with SerpAPI for {company_name}: {e}")
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
            phones = set(re.findall(r'\+?\d{1,4}?[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}', text))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return list(emails), list(phones)
