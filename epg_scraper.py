#!/usr/bin/env python3
"""
EPG Scraper - Downloads and processes EPG data from XML sources
Saves channel schedules as JSON files to GitHub repository
"""

import gzip
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.request import urlopen, Request
import logging

# Configuration
EPG_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_ID1.xml.gz",
    # Add more URLs here as needed
]

TIMEZONE_OFFSET = "+0700"  # Indonesian time
CHANNEL_LIST_FILE = "channel.txt"
LOG_FILE = "scrape.log"
OUTPUT_BASE_DIR = "schedule"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def parse_datetime(dt_string: str) -> datetime:
    """
    Parse datetime string from EPG format: 20260204003000 +0700
    Returns: datetime object
    """
    # Remove timezone offset for parsing
    dt_part = dt_string.split()[0]
    # Format: YYYYMMDDHHmmss
    return datetime.strptime(dt_part, "%Y%m%d%H%M%S")


def format_time(dt: datetime) -> str:
    """Format datetime to HH:MM:SS string"""
    return dt.strftime("%H:%M:%S")


def format_date(dt: datetime) -> str:
    """Format datetime to YYYY-MM-DD string"""
    return dt.strftime("%Y-%m-%d")


def sanitize_filename(name: str) -> str:
    """
    Convert channel name to valid filename
    Example: "AXN HD" -> "axn-hd.json"
    """
    # Replace spaces with hyphens, convert to lowercase
    name = name.strip().replace(" ", "-").lower()
    # Remove special characters except hyphens
    name = "".join(c for c in name if c.isalnum() or c == "-")
    return f"{name}.json"


def download_and_extract_xml(url: str) -> Optional[str]:
    """
    Download .gz file from URL and extract XML content
    Returns: XML string or None on failure
    """
    try:
        logger.info(f"Downloading from: {url}")
        
        # Create request with headers to avoid 403 Forbidden
        from urllib.request import Request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        }
        
        request = Request(url, headers=headers)
        with urlopen(request, timeout=60) as response:
            gz_data = response.read()
        
        logger.info(f"Extracting XML from gzip archive...")
        xml_content = gzip.decompress(gz_data).decode('utf-8')
        logger.info(f"Successfully extracted XML ({len(xml_content)} bytes)")
        return xml_content
    
    except Exception as e:
        logger.error(f"Failed to download/extract from {url}: {e}")
        return None


def parse_epg_xml(xml_content: str) -> tuple[Dict[str, str], Dict[str, List]]:
    """
    Parse EPG XML and extract channels and programs
    Returns: (channels_dict, programs_dict)
        channels_dict: {channel_id: channel_name}
        programs_dict: {channel_id: [program_list]}
    """
    try:
        root = ET.fromstring(xml_content)
        
        # Parse channels
        channels = {}
        for channel in root.findall('channel'):
            channel_id = channel.get('id')
            display_name = channel.find('display-name')
            if channel_id and display_name is not None:
                channels[channel_id] = display_name.text.strip()
        
        logger.info(f"Found {len(channels)} channels in XML")
        
        # Parse programs
        programs = {}
        for programme in root.findall('programme'):
            channel_id = programme.get('channel')
            if not channel_id:
                continue
            
            if channel_id not in programs:
                programs[channel_id] = []
            
            # Extract program details
            title_elem = programme.find('title')
            episode_elem = programme.find('episode-num')
            
            program_data = {
                'start': programme.get('start'),
                'stop': programme.get('stop'),
                'title': title_elem.text.strip() if title_elem is not None else 'Unknown',
                'episode_num': episode_elem.text.strip() if episode_elem is not None else ''
            }
            programs[channel_id].append(program_data)
        
        logger.info(f"Found programs for {len(programs)} channels")
        return channels, programs
    
    except Exception as e:
        logger.error(f"Failed to parse XML: {e}")
        return {}, {}


def load_channel_list(filename: str) -> List[tuple[str, str]]:
    """
    Load channel list from text file
    Returns: List of (channel_id, channel_name) tuples
    """
    channels = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Parse: "channel_id, channel_name" or just "channel_id"
                parts = [p.strip() for p in line.split(',', 1)]
                if len(parts) == 2:
                    channels.append((parts[0], parts[1]))
                else:
                    # Use channel_id as name if only one part
                    channels.append((parts[0], parts[0]))
        
        logger.info(f"Loaded {len(channels)} channels from {filename}")
        return channels
    
    except FileNotFoundError:
        logger.error(f"Channel list file not found: {filename}")
        return []
    except Exception as e:
        logger.error(f"Error reading channel list: {e}")
        return []


def find_channel_id(target_id: str, target_name: str, 
                    available_channels: Dict[str, str]) -> Optional[str]:
    """
    Find matching channel ID from available channels
    Tries exact ID match first, then case-insensitive name match
    """
    # Try exact channel ID match
    if target_id in available_channels:
        return target_id
    
    # Try case-insensitive name match
    target_name_lower = target_name.lower()
    for channel_id, channel_name in available_channels.items():
        if channel_name.lower() == target_name_lower:
            return channel_id
    
    return None


def filter_programs_by_date(programs: List[dict], target_date: str) -> List[dict]:
    """
    Filter programs that occur on the target date
    Returns list of programs formatted for JSON output
    """
    filtered = []
    
    for prog in programs:
        try:
            start_dt = parse_datetime(prog['start'])
            stop_dt = parse_datetime(prog['stop'])
            prog_date = format_date(start_dt)
            
            # Check if program is on target date
            if prog_date == target_date:
                filtered.append({
                    'show_name': prog['title'],
                    'start_time': format_time(start_dt),
                    'end_time': format_time(stop_dt),
                    'episode_number': prog['episode_num']
                })
        except Exception as e:
            logger.warning(f"Failed to parse program datetime: {e}")
            continue
    
    return filtered


def get_today_tomorrow_dates() -> tuple[str, str]:
    """
    Get today and tomorrow dates in Indonesian timezone
    Returns: (today_date, tomorrow_date) as YYYY-MM-DD strings
    """
    # Since the EPG data is already in +0700, we can use current system time
    # and just ensure we're working with the correct dates
    now = datetime.now()
    today = format_date(now)
    tomorrow = format_date(now + timedelta(days=1))
    
    logger.info(f"Processing dates - Today: {today}, Tomorrow: {tomorrow}")
    return today, tomorrow


def save_schedule_json(channel_name: str, date_type: str, date: str, programs: List[dict]):
    """
    Save channel schedule to JSON file
    date_type: 'today' or 'tomorrow'
    """
    # Create directory structure
    output_dir = Path(OUTPUT_BASE_DIR) / date_type
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename
    filename = sanitize_filename(channel_name)
    filepath = output_dir / filename
    
    # Prepare JSON data
    data = {
        'channel_name': channel_name,
        'date': date,
        'programs': programs
    }
    
    # Save to file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved {len(programs)} programs to {filepath}")


def main():
    """Main execution function"""
    logger.info("=" * 70)
    logger.info("EPG Scraper Started")
    logger.info("=" * 70)
    
    # Load channel list
    target_channels = load_channel_list(CHANNEL_LIST_FILE)
    if not target_channels:
        logger.error("No channels to process. Exiting.")
        return 1
    
    # Get dates
    today, tomorrow = get_today_tomorrow_dates()
    
    # Download and parse EPG data from sources
    all_channels = {}
    all_programs = {}
    
    for url in EPG_URLS:
        xml_content = download_and_extract_xml(url)
        if not xml_content:
            logger.warning(f"Skipping source: {url}")
            continue
        
        channels, programs = parse_epg_xml(xml_content)
        
        # Merge channels (only add if not already present)
        for ch_id, ch_name in channels.items():
            if ch_id not in all_channels:
                all_channels[ch_id] = ch_name
        
        # Merge programs (only add if not already present)
        for ch_id, prog_list in programs.items():
            if ch_id not in all_programs:
                all_programs[ch_id] = prog_list
    
    if not all_channels:
        logger.error("No EPG data available from any source. Exiting.")
        return 1
    
    logger.info(f"Total channels available: {len(all_channels)}")
    logger.info(f"Total channels with programs: {len(all_programs)}")
    
    # Process each target channel
    success_count = 0
    fail_count = 0
    
    for target_id, target_name in target_channels:
        logger.info(f"\nProcessing: {target_name} (ID: {target_id})")
        
        # Find matching channel
        matched_id = find_channel_id(target_id, target_name, all_channels)
        
        if not matched_id:
            logger.warning(f"Channel not found: {target_name} (ID: {target_id})")
            fail_count += 1
            continue
        
        if matched_id not in all_programs:
            logger.warning(f"No programs found for: {target_name}")
            fail_count += 1
            continue
        
        # Get actual channel name from EPG
        actual_name = all_channels[matched_id]
        programs = all_programs[matched_id]
        
        logger.info(f"Matched to: {actual_name} ({len(programs)} total programs)")
        
        # Filter and save today's schedule
        today_programs = filter_programs_by_date(programs, today)
        if today_programs:
            save_schedule_json(actual_name, 'today', today, today_programs)
        else:
            logger.warning(f"No programs for today ({today})")
        
        # Filter and save tomorrow's schedule
        tomorrow_programs = filter_programs_by_date(programs, tomorrow)
        if tomorrow_programs:
            save_schedule_json(actual_name, 'tomorrow', tomorrow, tomorrow_programs)
        else:
            logger.warning(f"No programs for tomorrow ({tomorrow})")
        
        if today_programs or tomorrow_programs:
            success_count += 1
        else:
            fail_count += 1
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("EPG Scraper Completed")
    logger.info(f"Successfully processed: {success_count} channels")
    logger.info(f"Failed/No data: {fail_count} channels")
    logger.info("=" * 70)
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
