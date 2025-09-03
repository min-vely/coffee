import json
import os
import re
from collections import defaultdict

def clean_ediya_data():
    """
    Loads the Ediya menu data, finds items with duplicate names,
    and appends '(디카페인)' to the one with less caffeine.
    """
    print("Starting Ediya data cleaning process...")
    
    ediya_path = os.path.join('data', 'ediya_menu.json')
    
    try:
        with open(ediya_path, 'r', encoding='utf-8') as f:
            ediya_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {ediya_path} not found. Please run the ediya_crawler.py first.")
        return

    # Group items by name
    items_by_name = defaultdict(list)
    for index, item in enumerate(ediya_data):
        # Normalize name by removing existing (디카페인) tags for idempotency
        normalized_name = item['name'].replace(' (디카페인)', '').strip()
        items_by_name[normalized_name].append({'index': index, 'item': item})

    modified_count = 0
    for name, items in items_by_name.items():
        if len(items) > 1: # Found duplicates
            print(f"  - Found duplicate name: '{name}'. Comparing {len(items)} items.")
            
            # Find the item with the minimum caffeine content
            min_caffeine_item_info = None
            min_caffeine_value = float('inf')

            for item_info in items:
                try:
                    caffeine_str = item_info['item'].get('nutrition', {}).get('카페인', '0')
                    caffeine_val = int(re.search(r'\d+', str(caffeine_str)).group()) if re.search(r'\d+', str(caffeine_str)) else 0
                    
                    if caffeine_val < min_caffeine_value:
                        min_caffeine_value = caffeine_val
                        min_caffeine_item_info = item_info

                except (ValueError, AttributeError) as e:
                    print(f"    - Could not parse caffeine for an item: {e}")
                    continue
            
            # Label all non-minimum caffeine items as regular and the minimum as decaf
            if min_caffeine_item_info:
                for item_info in items:
                    original_index = item_info['index']
                    # First, remove any existing tags
                    ediya_data[original_index]['name'] = name
                    # Then, add the tag to the decaf one
                    if item_info['index'] == min_caffeine_item_info['index']:
                        ediya_data[original_index]['name'] += " (디카페인)"
                        modified_count += 1
                        print(f"    - Appended '(디카페인)' to item at index {original_index} (Caffeine: {min_caffeine_value}mg)")

    if modified_count > 0:
        with open(ediya_path, 'w', encoding='utf-8') as f:
            json.dump(ediya_data, f, ensure_ascii=False, indent=4)
        print(f"\nData cleaning complete. Modified {modified_count} item(s). '{ediya_path}' has been updated.")
    else:
        print("\nNo duplicate items requiring modification were found.")

if __name__ == "__main__":
    clean_ediya_data()
