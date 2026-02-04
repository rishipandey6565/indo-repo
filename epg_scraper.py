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

def main():
    logging.info("Starting EPG Scrape run.")
    
    target_channels = load_target_channels()
    if not target_channels:
        logging.warning("No target channels found. Exiting.")
        return

    # Define Timezone
    tz = ZoneInfo(TIMEZONE)
    now_local = datetime.now(tz)
    
    # Define the two "Days" we want to capture (Today and Tomorrow)
    # We define strict start/end boundaries for these days
    today_date = now_local.date()
    tomorrow_date = today_date + timedelta(days=1)
    
    # Create Day Objects with Start (00:00) and End (23:59:59) boundaries
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

    # Initialize data structures for each channel in each day
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

                # Convert to local time for comparison
                start_local = start_dt.astimezone(tz)
                stop_local = stop_dt.astimezone(tz)

                # --- CHECK OVERLAPS FOR TODAY AND TOMORROW ---
                for day_key, day_info in target_days.items():
                    day_start = day_info["start"]
                    day_end = day_info["end"]

                    # LOGIC: Does the show overlap with this day?
                    # It overlaps if: Start is before DayEnd AND End is after DayStart
                    if start_local < day_end and stop_local > day_start:
                        
                        # Extract Details
                        title = programme.find("title").text if programme.find("title") is not None else "Unknown Title"
                        episode = programme.find("episode-num").text if programme.find("episode-num") is not None else ""
                        
                        # --- CLAMPING LOGIC ---
                        # If show started BEFORE this day (yesterday), set display time to 00:00:00
                        if start_local < day_start:
                            display_start = "00:00:00"
                        else:
                            display_start = start_local.strftime("%H:%M:%S")

                        # We keep the actual end time (even if it spills to next day), 
                        # as is standard for EPGs, unless you want that clamped too.
                        display_end = stop_local.strftime("%H:%M:%S")

                        entry = {
                            "show_name": title,
                            "start_time": display_start,
                            "end_time": display_end,
                            "episode_number": episode
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
            # If no programs found for a channel on this day, skip or write empty? 
            # Usually better to skip empty files, but we will write them to be safe.
            if not programs:
                continue

            # Sort programs by start time (handling the 00:00:00 correctly)
            # We sort by the string, which works because "00:00:00" is lexicographically first
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
