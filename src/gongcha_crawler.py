from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json
import os
import time
import re

def create_driver():
    """Creates and returns a new, configured Selenium WebDriver instance."""
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--log-level=3')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=service, options=options)

def get_gongcha_menu():
    """
    Crawls all Gong Cha categories sequentially, completing each one before starting the next,
    and adds the category name to each menu item.
    """
    print("Starting Gong Cha menu crawling (with Category data)...")

    categories = [
        {"name": "New 시즌 메뉴", "id": "001001"},
        {"name": "베스트셀러", "id": "001002"},
        {"name": "밀크티", "id": "001006"},
        {"name": "스무디", "id": "001010"},
        {"name": "오리지널 티", "id": "001003"},
        {"name": "프룻티&모어", "id": "001015"},
        {"name": "커피", "id": "001011"}
    ]
    
    all_menu_data = []
    seen_urls = set()
    base_url = "https://www.gong-cha.co.kr/brand/menu/product?category="
    FLEXIBLE_LINK_SELECTOR = 'div#product_list a[href*="product_detail"]'

    for category in categories:
        driver = None
        category_name = category["name"]
        category_id = category["id"]
        category_url = f"{base_url}{category_id}"
        print(f"\n--- Processing Category: {category_name} ---")
        
        # Step 1 for this category: Get URLs
        drink_urls_for_category = []
        try:
            driver = create_driver()
            driver.get(category_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, FLEXIBLE_LINK_SELECTOR)))
            link_elements = driver.find_elements(By.CSS_SELECTOR, FLEXIBLE_LINK_SELECTOR)
            print(f"  - Found {len(link_elements)} links.")
            for link in link_elements:
                href = link.get_attribute('href')
                if href and href not in seen_urls:
                    drink_urls_for_category.append(href)
                    seen_urls.add(href)
        except TimeoutException:
            print(f"  - No items found or timeout for category: {category_name}. Skipping.")
            if driver: driver.quit()
            continue
        except Exception as e:
            print(f"  - An error occurred during URL collection: {e}")
            if driver: driver.quit()
            continue
        finally:
            if driver: driver.quit()

        # Step 2 for this category: Scrape URLs
        if not drink_urls_for_category:
            continue
        
        print(f"  - Scraping {len(drink_urls_for_category)} items...")
        driver = None
        try:
            driver = create_driver()
            for url in drink_urls_for_category:
                try:
                    driver.get(url)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.menu-detail-conts")))
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    
                    name = soup.select_one("div.text-a p.t1").get_text(strip=True)
                    description = soup.select_one("div.text-a p.t2").get_text(strip=True)
                    image_url_path = soup.select_one("div.picture img")['src']
                    
                    raw_nutrition_info = {}
                    table = soup.select_one("div.table-item table")
                    if table:
                        headers = [th.get_text(strip=True) for th in table.select("thead th")][2:]
                        values = [td.get_text(strip=True) for td in table.select("tbody td")][2:]
                        raw_nutrition_info = dict(zip(headers, values))

                    formatted_nutrition_info = {}
                    for key, value in raw_nutrition_info.items():
                        if not value or value == '-': continue
                        clean_key = key.split('(')[0].strip()
                        new_value = value
                        if clean_key == '열량': clean_key = '칼로리'
                        if clean_key == '칼로리': new_value = f"{value}kcal"
                        elif clean_key in ['당류', '단백질', '포화지방']: new_value = f"{value}g"
                        elif clean_key in ['나트륨', '카페인']: new_value = f"{value}mg"
                        formatted_nutrition_info[clean_key] = new_value

                    menu_data = {
                        "brand": "Gong Cha",
                        "name": name,
                        "category": category_name, # Added category key
                        "image_url": f"https://www.gong-cha.co.kr{image_url_path}",
                        "description": description, 
                        "price": "Price not found.",
                        "nutrition": formatted_nutrition_info
                    }
                    all_menu_data.append(menu_data)
                except Exception as e:
                    print(f"\n    - Error processing URL {url}: {e}")
        finally:
            if driver: driver.quit()

    # --- Save Final Data ---
    data_dir = 'C:/Users/SBA/github/coffee/data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    file_path = os.path.join(data_dir, 'gongcha_menu.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_menu_data, f, ensure_ascii=False, indent=4)
    print(f"\nCrawling complete. {len(all_menu_data)} items saved to {file_path}")

if __name__ == '__main__':
    get_gongcha_menu()