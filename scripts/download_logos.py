import os
import json
import requests
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_UPLOAD_URL = "https://tvjadwal.id//wp-content/uploads"
SCHEDULE_DIRS = ["schedule/today", "schedule/tomorrow"]
DOWNLOAD_ROOT = "downloaded-images"
MAX_WORKERS = 10


def extract_filename_from_url(url: str) -> str:
    """
    Extract filename from `text=` query param.
    Example:
    https://placehold.co/...?...text=CVDPC
    -> CVDPC.svg
    """
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)
    text_value = query_params.get("text", ["logo"])[0]
    safe_name = "".join(c for c in text_value if c.isalnum() or c in ("-", "_"))
    return f"{safe_name}.svg"


def download_svg(url: str, save_path: Path):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()

        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "wb") as f:
            f.write(response.content)

        print(f"Downloaded: {save_path}")
    except Exception as e:
        print(f"Error downloading {url}: {e}")


def process_json_file(json_path: Path, day_type: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    channel_name = data["channel_name"].lower().replace(" ", "-")
    programs = data.get("programs", [])

    unique_urls = {}
    for program in programs:
        url = program.get("show_logo")
        if url:
            filename = extract_filename_from_url(url)
            unique_urls[url] = filename

    # Download all unique logos in parallel
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for url, filename in unique_urls.items():
            save_path = Path(DOWNLOAD_ROOT) / channel_name / day_type / filename
            futures.append(executor.submit(download_svg, url, save_path))

        for future in as_completed(futures):
            future.result()

    # Update JSON URLs
    for program in programs:
        url = program.get("show_logo")
        if url and url in unique_urls:
            filename = unique_urls[url]
            new_path = f"{BASE_UPLOAD_URL}/{DOWNLOAD_ROOT}/{channel_name}/{day_type}/{filename}"
            program["show_logo"] = new_path

    # Write updated JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Updated JSON: {json_path}")


def main():
    for schedule_dir in SCHEDULE_DIRS:
        day_type = Path(schedule_dir).name  # today or tomorrow
        dir_path = Path(schedule_dir)

        if not dir_path.exists():
            continue

        for json_file in dir_path.glob("*.json"):
            process_json_file(json_file, day_type)


if __name__ == "__main__":
    main()
