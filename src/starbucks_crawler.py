import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import json
import os
import re
import time

def get_starbucks_menu():
    """
    Crawls the Starbucks Korea website to get detailed drink information.
    1. Uses Selenium to load the dynamic drink list page to get product IDs.
    2. For each drink, uses Selenium to navigate to its detail page.
    3. Fetches description and nutrition info from the fully rendered detail page.
    4. Saves the collected data into 'data/starbucks_menu.json'.
    """
    print("Starting Starbucks menu crawling with Selenium...")

    drink_list_url = "https://www.starbucks.co.kr/menu/drink_list.do"
    drink_view_url_base = "https://www.starbucks.co.kr/menu/drink_view.do?product_cd="
    
    product_ids_and_names = []
    try:
        print("Setting up Selenium WebDriver to fetch product list...")
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
        driver = webdriver.Chrome(service=service, options=options)
        
        print(f"Navigating to {drink_list_url}...")
        driver.get(drink_list_url)
        
        print("Waiting for list page to load...")
        time.sleep(5)

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        menu_items = soup.select('li.menuDataSet')

        if not menu_items:
            print("Could not find menu items on the list page.")
            return
        
        print(f"Found {len(menu_items)} drinks. Extracting product info...")
        for item in menu_items:
            name = item.select_one('dd').get_text(strip=True)
            product_id_tag = item.select_one('a.goDrinkView')
            img_tag = item.select_one('img')
            
            if product_id_tag and product_id_tag.has_attr('prod'):
                product_id = product_id_tag['prod']
                image_url = img_tag['src'] if img_tag and img_tag.has_attr('src') else ''
                product_ids_and_names.append({"id": product_id, "name": name, "image_url": image_url})

    except Exception as e:
        print(f"An error occurred while fetching the product list: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()
            print("WebDriver for list page closed.")

    if not product_ids_and_names:
        print("No products found. Exiting.")
        return

    all_menu_data = []
    print(f"\nStarting to fetch details for {len(product_ids_and_names)} products using Selenium...")

    try:
        print("Setting up Selenium WebDriver for detail pages...")
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
        driver = webdriver.Chrome(service=service, options=options)

        for product in product_ids_and_names:
            product_id = product["id"]
            name = product["name"]
            image_url = product["image_url"]
            try:
                detail_url = f"{drink_view_url_base}{product_id}"
                driver.get(detail_url)
                time.sleep(1) # A small wait for dynamic content

                detail_soup = BeautifulSoup(driver.page_source, 'html.parser')

                description_tag = detail_soup.select_one('p.t1')
                description = description_tag.get_text(strip=True) if description_tag else ""

                # Scrape all available nutrition data into a temporary dictionary
                temp_nutrition_info = {}
                nutrition_list = detail_soup.select('div.product_info_content li')
                for li in nutrition_list:
                    dt = li.find('dt')
                    dd = li.find('dd')
                    if dt and dd and dd.text.strip():
                        key = dt.get_text(strip=True)
                        value = dd.get_text(strip=True)
                        clean_key = re.sub(r'\s*\(.*\)\s*', '', key).strip()
                        if '1회 제공량' in clean_key:
                            clean_key = '칼로리'
                        temp_nutrition_info[clean_key] = value

                # Create the final, ordered dictionary with units
                ordered_keys = ['칼로리', '당류', '단백질', '포화지방', '나트륨', '카페인']
                nutrition_info = {}
                for key in ordered_keys:
                    if key in temp_nutrition_info:
                        value = temp_nutrition_info[key]
                        if value and value != '-':
                            if key == '칼로리':
                                unit = 'kcal'
                            elif key in ['당류', '단백질', '포화지방']:
                                unit = 'g'
                            elif key in ['나트륨', '카페인']:
                                unit = 'mg'
                            else:
                                unit = ''
                            nutrition_info[key] = f"{value}{unit}"
                        else:
                            nutrition_info[key] = value # Keep empty or '-' as is

                menu_data = {
                    "brand": "Starbucks",
                    "name": name,
                    "product_id": product_id,
                    "image_url": image_url,
                    "description": description,
                    "price": "Price not found.",
                    "nutrition": nutrition_info
                }
                all_menu_data.append(menu_data)
                print(f"  - Fetched: {name}")

            except Exception as e:
                print(f"  - Error processing product {name} (ID: {product_id}): {e}")
                continue
    
    except Exception as e:
        print(f"A critical error occurred during detail page processing: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()
            print("WebDriver for detail pages closed.")

    data_dir = 'C:/Users/SBA/github/coffee/data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    file_path = os.path.join(data_dir, 'starbucks_menu.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_menu_data, f, ensure_ascii=False, indent=4)

    print(f"\nCrawling complete. {len(all_menu_data)} items saved to {file_path}")

if __name__ == '__main__':
    get_starbucks_menu()