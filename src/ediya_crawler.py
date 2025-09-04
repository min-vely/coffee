from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json
import os
import time

def get_ediya_menu():
    """
    Crawls the Ediya Coffee website by simulating checkbox clicks for each category,
    re-finding elements in each loop to prevent stale element errors.
    """
    print("Starting Ediya menu crawling (Stale-Proof Strategy)...")

    base_url = "https://ediya.com/contents/drink.html"
    all_menu_data = []
    driver = None

    try:
        print("Setting up WebDriver...")
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(service=service, options=options)
        
        print(f"Navigating to {base_url}")
        driver.get(base_url)
        time.sleep(3)

        # First, get a count of categories to loop through
        initial_labels = driver.find_elements(By.CSS_SELECTOR, ".menu_sch ul li label")
        category_count = len(initial_labels)
        print(f"Found {category_count} total category labels.")

        for i in range(category_count):
            # In each iteration, re-find all the labels to get fresh elements
            labels = driver.find_elements(By.CSS_SELECTOR, ".menu_sch ul li label")
            if i >= len(labels):
                print("Error: Index out of bounds while finding labels. Breaking.")
                break

            label = labels[i]
            category_name = label.text
            
            if category_name == "TOPPING":
                print("\n--- Skipping Category: TOPPING ---")
                continue

            print(f"\n--- Processing Category: {category_name} ---")
            input_id = label.get_attribute("for")

            # Uncheck all checkboxes
            all_checkboxes = driver.find_elements(By.CSS_SELECTOR, ".menu_sch ul li input[type='checkbox']")
            for chk in all_checkboxes:
                try:
                    if chk.is_selected():
                        driver.execute_script("arguments[0].click();", chk)
                except StaleElementReferenceException:
                    # This can happen if the page refreshes while unchecking. It's okay to ignore.
                    pass
            
            # Click the target category checkbox
            target_checkbox = driver.find_element(By.ID, input_id)
            driver.execute_script("arguments[0].click();", target_checkbox)
            time.sleep(2) # Wait for the page to filter

            # Click the 'More' button until it's gone
            while True:
                try:
                    more_button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "div.con_btn > a.line_btn"))
                    )
                    driver.execute_script("arguments[0].click();", more_button)
                    time.sleep(1)
                except (TimeoutException, NoSuchElementException):
                    print("  - All items loaded for this category.")
                    break

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            menu_items = soup.select("#menu_ul > li")
            print(f"  - Found {len(menu_items)} items.")

            for item in menu_items:
                try:
                    img_tag = item.select_one('a[onclick^="show_nutri"] > img')
                    image_url = img_tag['src'] if img_tag and img_tag.has_attr('src') else ""

                    detail_div = item.find('div', class_='pro_detail')
                    if not detail_div: continue

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
                        "category": category_name,
                        "image_url": f"https://www.ediya.com{image_url}",
                        "description": description,
                        "price": "Price not found.",
                        "nutrition": nutrition_info
                    }
                    all_menu_data.append(menu_data)

                except Exception as e:
                    print(f"    - An error occurred for an item: {e}")
                    continue

    except Exception as e:
        print(f"A critical error occurred: {e}")
    finally:
        if driver: driver.quit()

    data_dir = 'C:/Users/SBA/github/coffee/data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    file_path = os.path.join(data_dir, 'ediya_menu.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_menu_data, f, ensure_ascii=False, indent=4)

    print(f"\nCrawling complete. {len(all_menu_data)} items saved to {file_path}")

if __name__ == '__main__':
    get_ediya_menu()