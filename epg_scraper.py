import os
import gzip
import json
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import re
import io

# --- Configuration ---
EPG_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_ID1.xml.gz",
]

CHANNEL_FILE = "channel.txt"
LOG_FILE = "scrape.log"
OUTPUT_DIR_TODAY = "schedule/today"
OUTPUT_DIR_TOMORROW = "schedule/tomorrow"
TIMEZONE = "Asia/Jakarta"

# Setup Logging
logging.basicConfig(
    filename=LOG_FILE,
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def sanitize_filename(name):
    name = name.strip().replace(" ", "-")
    return re.sub(r'[^a-zA-Z0-9\-]', '', name)

def generate_show_logo(show_name):
    """
    Generate a placehold.co logo URL from show name.
    Example: "Game Of Throne" -> "https://placehold.co/100x100/dc2626/ffffff?text=GOT"
    Example: "S.W.A.T." -> "https://placehold.co/100x100/dc2626/ffffff?text=SWAT"
    """
    # Extract initials from the show name
    words = show_name.strip().split()
    
    # Take first letter of each word, uppercase
    initials = ''.join([word[0].upper() for word in words if word])
    
    # Limit to reasonable length (e.g., max 5 characters)
    initials = initials[:5]
    
    # Generate URL
    logo_url = f"https://placehold.co/100x100/dc2626/ffffff?text={initials}"
    
    return logo_url

def parse_epg_timestamp(ts_str):
    try:
        return datetime.strptime(ts_str, "%Y%m%d%H%M%S %z")
    except ValueError as e:
        logging.error(f"Failed to parse timestamp {ts_str}: {e}")
        return None

def load_target_channels():
    targets = {}
    if not os.path.exists(CHANNEL_FILE):
        return targets
    try:
        with open(CHANNEL_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    targets[parts[0].strip()] = parts[1].strip()
    except Exception as e:
        logging.error(f"Error reading channel file: {e}")
    return targets

def extract_episode_from_title(title, current_episode):
    """
    If current_episode is empty, checks title for 'Eps.1' pattern.
    Returns tuple (clean_title, episode_number)
    """
    if current_episode:
        return title, current_episode

    # Regex logic:
    # 1. ^(.*?)       -> Capture the start as the Show Name (Group 1)
    # 2. [\s\-]+      -> Match separator (space or hyphen)
    # 3. (Eps\.?\s* -> Match 'Eps' or 'Eps.' followed by optional space
    # 4. (\d+))$      -> Capture the number (Group 3) at the end of string
    match = re.search(r'^(.*?)[\s\-]+(Eps\.?\s*(\d+))$', title, re.IGNORECASE)
    
    if match:
        clean_title = match.group(1).strip()
        # Format as requested: "Eps -1"
        new_episode = f"Eps -{match.group(3)}"
        return clean_title, new_episode
    
    return title, ""

def main():
    logging.info("Starting EPG Scrape run.")
    
    target_channels = load_target_channels()
    if not target_channels:
        logging.warning("No target channels found. Exiting.")
        return

    tz = ZoneInfo(TIMEZONE)
    now_local = datetime.now(tz)
    
    today_date = now_local.date()
    tomorrow_date = today_date + timedelta(days=1)
    
    target_days = {
        "today": {
            "date_obj": today_date,
            "start": datetime.combine(today_date, time.min).replace(tzinfo=tz),
            "end": datetime.combine(today_date, time.max).replace(tzinfo=tz),
            "output_dir": OUTPUT_DIR_TODAY,
            "data": {} 
        },
        "tomorrow": {
            "date_obj": tomorrow_date,
            "start": datetime.combine(tomorrow_date, time.min).replace(tzinfo=tz),
            "end": datetime.combine(tomorrow_date, time.max).replace(tzinfo=tz),
            "output_dir": OUTPUT_DIR_TOMORROW,
            "data": {}
        }
    }

    for day_key in target_days:
        for cid in target_channels:
            target_days[day_key]["data"][cid] = []

    for url in EPG_URLS:
        logging.info(f"Fetching {url}...")
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz:
                xml_content = gz.read()
            
            root = ET.fromstring(xml_content)

            for programme in root.findall('programme'):
                channel_id = programme.get('channel')
                
                if channel_id not in target_channels:
                    continue

                start_raw = programme.get('start')
                stop_raw = programme.get('stop')
                start_dt = parse_epg_timestamp(start_raw)
                stop_dt = parse_epg_timestamp(stop_raw)

                if not start_dt or not stop_dt:
                    continue

                start_local = start_dt.astimezone(tz)
                stop_local = stop_dt.astimezone(tz)

                for day_key, day_info in target_days.items():
                    day_start = day_info["start"]
                    day_end = day_info["end"]

                    if start_local < day_end and stop_local > day_start:
                        
                        # --- Extraction & Cleaning Logic ---
                        title_text = programme.find("title").text if programme.find("title") is not None else "Unknown Title"
                        episode_text = programme.find("episode-num").text if programme.find("episode-num") is not None else ""
                        
                        # Apply new helper function to extract Eps from title
                        final_title, final_episode = extract_episode_from_title(title_text, episode_text)
                        
                        # Generate logo URL for the show
                        show_logo = generate_show_logo(final_title)
                        
                        # --- Clamping Logic ---
                        if start_local < day_start:
                            display_start = "00:00:00"
                        else:
                            display_start = start_local.strftime("%H:%M:%S")

                        display_end = stop_local.strftime("%H:%M:%S")

                        entry = {
                            "show_name": final_title,
                            "show_logo": show_logo,
                            "start_time": display_start,
                            "end_time": display_end,
                            "episode_number": final_episode
                        }
                        
                        target_days[day_key]["data"][channel_id].append(entry)

        except Exception as e:
            logging.error(f"Failed to process {url}: {e}")

    # Write Files
    for day_key, day_info in target_days.items():
        out_dir = day_info["output_dir"]
        os.makedirs(out_dir, exist_ok=True)
        date_str = str(day_info["date_obj"])

        for cid, programs in day_info["data"].items():
            if not programs:
                continue

            programs.sort(key=lambda x: x["start_time"])

            c_name = target_channels.get(cid, cid)
            file_name = f"{sanitize_filename(c_name)}.json"
            file_path = os.path.join(out_dir, file_name)
            
            output_json = {
                "channel_name": c_name,
                "date": date_str,
                "programs": programs
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(output_json, f, indent=2, ensure_ascii=False)
    
    logging.info("Scrape finished.")

if __name__ == "__main__":
    main()
