
import os
import requests
from bs4 import BeautifulSoup
import re
import time

# Create directories
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "augments")
os.makedirs(ASSETS_DIR, exist_ok=True)

URL = "https://wiki.leagueoflegends.com/en-us/ARAM:_Mayhem/Augments"

def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def main():
    print(f"Fetching {URL}...")
    try:
        response = requests.get(URL)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch page: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Target the main content area
    content = soup.find(id="mw-content-text")
    if not content:
        print("Could not find main content.")
        return

    # Find all augment icon links
    # Pattern: <a ... title="..."> <img ... src="..."> </a>
    # The snippet showed: <a href="..." class="mw-file-description" title="An icon for the ARAM: Mayhem augment ADAPt">
    
    links = content.find_all('a', class_='mw-file-description')
    
    count = 0
    for link in links:
        title_attr = link.get('title', '')
        # Filter for "An icon for the ARAM: Mayhem augment ..."
        if "An icon for the ARAM: Mayhem augment" in title_attr:
            augment_name = title_attr.replace("An icon for the ARAM: Mayhem augment", "").strip()
            
            img_tag = link.find('img')
            if img_tag:
                src = img_tag.get('src', '')
                if not src:
                    continue
                
                # Handle relative URLs if necessary (usually they are absolute or root-relative)
                if src.startswith('/'):
                    img_url = "https://wiki.leagueoflegends.com" + src
                else:
                    img_url = src
                
                # Get higher resolution if possible (remove /thumb/ and the size prefix)
                # Example: /en-us/images/thumb/ADAPt_mayhem_augment.png/80px-ADAPt_mayhem_augment.png
                # Target: /en-us/images/ADAPt_mayhem_augment.png
                
                # But wiki structure is tricky. Let's try to just download the src as is first, 
                # or try to derive the full size URL.
                # Common pattern: /images/thumb/a/a1/Name.png/SIZEpx-Name.png
                # Full size: /images/a/a1/Name.png
                
                # Let's try downloading the 80px thumb first as it's sufficient for template matching usually,
                # but user might want better quality.
                
                # A simple heuristic for high-res:
                # remove "/thumb" and everything after the last slash in the directory path?
                # Actually, scraping the thumb is safer for now.
                
                try:
                    print(f"Downloading {augment_name}...")
                    img_data = requests.get(img_url).content
                    
                    filename = safe_filename(augment_name) + ".png"
                    filepath = os.path.join(ASSETS_DIR, filename)
                    
                    with open(filepath, 'wb') as f:
                        f.write(img_data)
                    
                    count += 1
                    time.sleep(0.1) # Be polite
                except Exception as e:
                    print(f"Failed to download {augment_name}: {e}")

    print(f"Done. Downloaded {count} augment icons to {ASSETS_DIR}")

if __name__ == "__main__":
    main()
