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
    Crawls the Starbucks Korea website to get detailed drink information, including category for each drink.
    It correctly associates drinks with their categories by parsing the dt/dd structure of the menu page.
    """
    print("Starting Starbucks menu crawling with correct category parsing...")

    drink_list_url = "https://www.starbucks.co.kr/menu/drink_list.do"
    
    # Phase 1: Collect product info including category
    products_with_category = []
    driver = None
    try:
        print("Setting up WebDriver to fetch product list and categories...")
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(service=service, options=options)
        
        print(f"Navigating to {drink_list_url}...")
        driver.get(drink_list_url)
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Find all category titles (dt tags)
        category_dts = soup.select('div.product_list > dl > dt')

        for dt in category_dts:
            category_tag = dt.find('a')
            if not category_tag:
                continue
            category_name = category_tag.get_text(strip=True)
            print(f"Processing category: {category_name}")
            
            # Find the list of drinks in the immediately following sibling <dd>
            drink_list_dd = dt.find_next_sibling('dd')
            if not drink_list_dd:
                continue

            menu_items = drink_list_dd.select('li.menuDataSet')
            print(f"  - Found {len(menu_items)} items.")
            for item in menu_items:
                name = item.select_one('dd').get_text(strip=True)
                product_id_tag = item.select_one('a.goDrinkView')
                img_tag = item.select_one('img')
                
                if product_id_tag and product_id_tag.has_attr('prod'):
                    product_id = product_id_tag['prod']
                    image_url = img_tag['src'] if img_tag and img_tag.has_attr('src') else ''
                    products_with_category.append({
                        "id": product_id, 
                        "name": name, 
                        "image_url": image_url,
                        "category": category_name
                    })

    except Exception as e:
        print(f"An error occurred while fetching the product list: {e}")
    finally:
        if driver: driver.quit()

    if not products_with_category:
        print("No products found. Exiting.")
        return

    # Phase 2: Scrape details for each product
    all_menu_data = []
    print(f"\nStarting to fetch details for {len(products_with_category)} products...")
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(service=service, options=options)

        for product in products_with_category:
            try:
                detail_url = f"https://www.starbucks.co.kr/menu/drink_view.do?product_cd={product['id']}"
                driver.get(detail_url)
                time.sleep(1)

                detail_soup = BeautifulSoup(driver.page_source, 'html.parser')
                description_tag = detail_soup.select_one('p.t1')
                description = description_tag.get_text(strip=True) if description_tag else ""

                temp_nutrition_info = {}
                nutrition_list = detail_soup.select('div.product_info_content li')
                for li in nutrition_list:
                    dt = li.find('dt')
                    dd = li.find('dd')
                    if dt and dd and dd.text.strip():
                        key = dt.get_text(strip=True)
                        value = dd.get_text(strip=True)
                        clean_key = re.sub(r'\s*\(.*\)\s*', '', key).strip()
                        if '1회 제공량' in clean_key: clean_key = '칼로리'
                        temp_nutrition_info[clean_key] = value

                ordered_keys = ['칼로리', '당류', '단백질', '포화지방', '나트륨', '카페인']
                nutrition_info = {}
                for key in ordered_keys:
                    if key in temp_nutrition_info:
                        value = temp_nutrition_info[key]
                        if value and value != '-':
                            if key == '칼로리': unit = 'kcal'
                            elif key in ['당류', '단백질', '포화지방']: unit = 'g'
                            elif key in ['나트륨', '카페인']: unit = 'mg'
                            else: unit = ''
                            nutrition_info[key] = f"{value}{unit}"
                        else:
                            nutrition_info[key] = value

                menu_data = {
                    "brand": "Starbucks",
                    "name": product["name"],
                    "category": product["category"],
                    "image_url": product["image_url"],
                    "description": description,
                    "price": "Price not found.",
                    "nutrition": nutrition_info
                }
                all_menu_data.append(menu_data)
                print(f"  - Fetched: {product['name']}")

            except Exception as e:
                print(f"  - Error processing product {product['name']} (ID: {product['id']}): {e}")
                continue
    
    except Exception as e:
        print(f"A critical error occurred during detail page processing: {e}")
    finally:
        if driver: driver.quit()

    data_dir = 'C:/Users/SBA/github/coffee/data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    file_path = os.path.join(data_dir, 'starbucks_menu.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_menu_data, f, ensure_ascii=False, indent=4)

    print(f"\nCrawling complete. {len(all_menu_data)} items saved to {file_path}")

if __name__ == '__main__':
    get_starbucks_menu()
