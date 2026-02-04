import os
import gzip
import json
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import io

# --- Configuration ---
# Add multiple URLs here
EPG_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_ID1.xml.gz",
    # "https://example.com/another_epg.xml.gz" 
]

CHANNEL_FILE = "channel.txt"
LOG_FILE = "scrape.log"
OUTPUT_DIR_TODAY = "schedule/today"
OUTPUT_DIR_TOMORROW = "schedule/tomorrow"
TIMEZONE = "Asia/Jakarta"

# Setup Logging
logging.basicConfig(
    filename=LOG_FILE,
    filemode='w', # Overwrite mode
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def sanitize_filename(name):
    """Sanitizes strings to be safe for filenames."""
    # Replace spaces with hyphens, remove special chars
    name = name.strip().replace(" ", "-")
    return re.sub(r'[^a-zA-Z0-9\-]', '', name)

def parse_epg_timestamp(ts_str):
    """Parses format: 20260204003000 +0700"""
    try:
        # datetime.strptime %z expects +HHMM without space usually, 
        # but modern python handles space or we can strip it.
        # The format in XML is "YYYYMMDDHHMMSS +HHMM"
        return datetime.strptime(ts_str, "%Y%m%d%H%M%S %z")
    except ValueError as e:
        logging.error(f"Failed to parse timestamp {ts_str}: {e}")
        return None

def load_target_channels():
    """Reads channel.txt and returns a dict mapping ID -> Name."""
    targets = {}
    if not os.path.exists(CHANNEL_FILE):
        logging.error(f"{CHANNEL_FILE} not found.")
        return targets

    try:
        with open(CHANNEL_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    c_id = parts[0].strip()
                    c_name = parts[1].strip()
                    targets[c_id] = c_name
    except Exception as e:
        logging.error(f"Error reading channel file: {e}")
    
    return targets

def main():
    logging.info("Starting EPG Scrape run.")
    
    # 1. Load Target Channels
    target_channels = load_target_channels()
    if not target_channels:
        logging.warning("No target channels found. Exiting.")
        return

    # 2. Define Time Windows (Today/Tomorrow in Jakarta)
    tz = ZoneInfo(TIMEZONE)
    now_local = datetime.now(tz)
    today_date = now_local.date()
    tomorrow_date = today_date + timedelta(days=1)
    
    logging.info(f"Processing for dates: Today={today_date}, Tomorrow={tomorrow_date}")

    # Prepare data structure: processed_data[date_str][channel_id] = {meta, programs}
    processed_data = {
        str(today_date): {},
        str(tomorrow_date): {}
    }

    # 3. Process URLs
    for url in EPG_URLS:
        logging.info(f"Fetching {url}...")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Decompress GZ in memory
            with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz:
                xml_content = gz.read()
            
            logging.info("Decompression successful. Parsing XML...")
            root = ET.fromstring(xml_content)

            # --- Parse Programs ---
            # We iterate over 'programme' tags.
            # We only care if the channel attribute matches our target list.
            for programme in root.findall('programme'):
                channel_id = programme.get('channel')
                
                if channel_id not in target_channels:
                    continue

                # Parse Times
                start_raw = programme.get('start')
                stop_raw = programme.get('stop')
                
                start_dt = parse_epg_timestamp(start_raw)
                stop_dt = parse_epg_timestamp(stop_raw)

                if not start_dt or not stop_dt:
                    continue

                # Convert to Target Timezone for Date Logic
                start_local = start_dt.astimezone(tz)
                stop_local = stop_dt.astimezone(tz)
                
                # Check which 'bucket' this program belongs to (Today or Tomorrow)
                prog_date_str = str(start_local.date())
                
                if prog_date_str not in processed_data:
                    continue # Skip if not today or tomorrow

                # Extract Details
                title_elem = programme.find("title")
                title = title_elem.text if title_elem is not None else "Unknown Title"
                
                ep_elem = programme.find("episode-num")
                episode = ep_elem.text if ep_elem is not None else ""

                # Format times for JSON (Time only)
                fmt_time = "%H:%M:%S"
                
                program_entry = {
                    "show_name": title,
                    "start_time": start_local.strftime(fmt_time),
                    "end_time": stop_local.strftime(fmt_time),
                    "episode_number": episode
                }

                # Add to structure
                if channel_id not in processed_data[prog_date_str]:
                    processed_data[prog_date_str][channel_id] = []
                
                processed_data[prog_date_str][channel_id].append(program_entry)

        except Exception as e:
            logging.error(f"Failed to process {url}: {e}")

    # 4. Write JSON Files
    for date_key, channels_data in processed_data.items():
        # Determine output directory
        if date_key == str(today_date):
            out_dir = OUTPUT_DIR_TODAY
        else:
            out_dir = OUTPUT_DIR_TOMORROW
            
        # Ensure dir exists
        os.makedirs(out_dir, exist_ok=True)

        for cid, programs in channels_data.items():
            c_name = target_channels.get(cid, cid)
            file_name = f"{sanitize_filename(c_name)}.json"
            file_path = os.path.join(out_dir, file_name)
            
            output_json = {
                "channel_name": c_name,
                "date": date_key,
                "programs": programs
            }
            
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(output_json, f, indent=2, ensure_ascii=False)
                logging.info(f"Saved {file_path}")
            except Exception as e:
                logging.error(f"Failed to write {file_path}: {e}")

    logging.info("Scrape finished.")

if __name__ == "__main__":
    main()
