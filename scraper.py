from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import requests
from bs4 import BeautifulSoup
import re
import time
import chromedriver_autoinstaller
chromedriver_autoinstaller.install()


def get_company_website(company_name):
    query = f"{company_name} official site"
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)

    driver.get(f"https://www.google.com/search?q={query}")
    time.sleep(2)

    try:
        result = driver.find_element(By.CSS_SELECTOR, 'div.yuRUbf > a')
        url = result.get_attribute('href')
    except Exception as e:
        print(f"Error finding website for {company_name}: {e}")
        url = None

    driver.quit()
    return url

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

