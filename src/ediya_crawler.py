from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json
import os
import time
import re

def get_ediya_menu():
    """
    Crawls the Ediya Coffee website to get drink information.
    1. Navigates to the drink menu page.
    2. Clicks the 'More' button repeatedly to load all drinks.
    3. Parses the fully loaded HTML to extract details for each drink from hidden divs.
    4. Saves the data to 'data/ediya_menu.json'.
    """
    print("Starting Ediya menu crawling...")
    
    menu_url = "https://ediya.com/contents/drink.html?chked_val=12,13,14,15,16,71,83,154,155,&skeyword=#blockcate"
    
    all_menu_data = []
    
    try:
        print("Setting up Selenium WebDriver...")
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(menu_url)
        
        print("Loading all menu items by clicking 'More'...")
        while True:
            try:
                more_button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "div.con_btn > a.line_btn"))
                )
                driver.execute_script("arguments[0].click();", more_button)
                time.sleep(1)
            except (TimeoutException, NoSuchElementException):
                print("No more 'More' button found. All items loaded.")
                break

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        menu_items = soup.select("#menu_ul > li")
        print(f"Found {len(menu_items)} items. Starting detail scraping...")

        for item in menu_items:
            try:
                # Extract image URL from the list item itself, using a more specific selector
                img_tag = item.select_one('a[onclick^="show_nutri"] > img')
                image_url = img_tag['src'] if img_tag and img_tag.has_attr('src') else ""

                detail_div = item.find('div', class_='pro_detail')
                if not detail_div:
                    continue

                name_tag = detail_div.select_one("div.detail_con > h2")
                name = name_tag.find(string=True, recursive=False).strip() if name_tag else "Name not found"
                
                description_tag = detail_div.select_one("div.detail_txt")
                description = description_tag.get_text(strip=True).replace('\n', ' ') if description_tag else ""

                nutrition_info = {}
                nutrition_dls = detail_div.select("div.pro_nutri > dl")
                for dl in nutrition_dls:
                    dt = dl.find('dt')
                    dd = dl.find('dd')
                    if dt and dd:
                        key = dt.get_text(strip=True)
                        value = dd.get_text(strip=True).replace('(', '').replace(')', '')
                        nutrition_info[key] = value
                
                menu_data = {
                    "brand": "Ediya",
                    "name": name,
                    "image_url": f"https://www.ediya.com{image_url}",
                    "description": description,
                    "price": "Price not found.",
                    "nutrition": nutrition_info
                }
                all_menu_data.append(menu_data)
                print(f"  - Fetched: {name}")

            except Exception as e:
                print(f"  - An error occurred for an item: {e}")
                continue

    except Exception as e:
        print(f"A critical error occurred: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()
            print("WebDriver closed.")

    data_dir = 'C:/Users/SBA/github/coffee/data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    file_path = os.path.join(data_dir, 'ediya_menu.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_menu_data, f, ensure_ascii=False, indent=4)

    print(f"\nCrawling complete. {len(all_menu_data)} items saved to {file_path}")

if __name__ == '__main__':
    get_ediya_menu()