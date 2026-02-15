import os
import json
import requests
import concurrent.futures
import hashlib
from pathlib import Path

# --- Configuration ---
BASE_URL = "https://example.com/wp-content/uploads"
SCHEDULE_DIRS = ["schedule/today", "schedule/tomorrow"]
DOWNLOAD_BASE_DIR = "downloaded-images"

def download_image(url, save_path):
    """
    Downloads the image from the URL to the save_path.
    Returns True if successful, False otherwise.
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Check if file already exists to avoid redundant network calls
        if os.path.exists(save_path):
            return True

        response = requests.get(url, stream=True, timeout=15)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return True
        else:
            print(f"Failed to download {url}: Status {response.status_code}")
    except Exception as e:
        print(f"Error downloading {url}: {e}")
    return False

def process_single_json_file(file_path):
    """
    Parses a single JSON file, downloads logos, and updates the file.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        channel_name = data.get("channel_name", "unknown").lower().replace(" ", "-")
        
        # Determine if 'today' or 'tomorrow' based on parent directory
        path_parts = Path(file_path).parts
        if "today" in path_parts:
            day_folder = "today"
        elif "tomorrow" in path_parts:
            day_folder = "tomorrow"
        else:
            day_folder = "other"

        # Dictionary to map { original_url : local_relative_path }
        # This prevents downloading the same logo twice for one file
        url_map = {}
        download_tasks = []

        programs = data.get("programs", [])
        
        # 1. Identify unique URLs to download
        for program in programs:
            original_url = program.get("show_logo")
            
            # Only process if it's a URL and not already our new domain
            if original_url and BASE_URL not in original_url:
                if original_url not in url_map:
                    # Generate a filename using MD5 hash of URL to ensure uniqueness and valid chars
                    file_hash = hashlib.md5(original_url.encode()).hexdigest()
                    filename = f"logo-{file_hash}.svg"
                    
                    # Construct relative path: downloaded-images/aniplus/today/logo-hash.svg
                    relative_path = f"{DOWNLOAD_BASE_DIR}/{channel_name}/{day_folder}/{filename}"
                    
                    url_map[original_url] = relative_path
                    download_tasks.append((original_url, relative_path))

        # 2. Download images using ThreadPoolExecutor
        # Adjust max_workers as needed
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(download_image, url, path) for url, path in download_tasks]
            concurrent.futures.wait(futures)

        # 3. Update the JSON data with new URLs
        updated = False
        for program in programs:
            original_url = program.get("show_logo")
            if original_url in url_map:
                relative_path = url_map[original_url]
                # Combine BASE_URL with relative path
                new_full_url = f"{BASE_URL}/{relative_path}"
                
                if program["show_logo"] != new_full_url:
                    program["show_logo"] = new_full_url
                    updated = True

        # 4. Save the updated JSON back to disk
        if updated:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            print(f"Updated: {file_path}")
        else:
            print(f"No changes needed: {file_path}")

    except Exception as e:
        print(f"Failed to process file {file_path}: {e}")

def main():
    # Gather all JSON files
    all_json_files = []
    for directory in SCHEDULE_DIRS:
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                if filename.endswith(".json"):
                    all_json_files.append(os.path.join(directory, filename))
    
    print(f"Found {len(all_json_files)} JSON files to process.")

    # Process files concurrently (Using threads for file I/O operations)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        executor.map(process_single_json_file, all_json_files)

if __name__ == "__main__":
    main()
