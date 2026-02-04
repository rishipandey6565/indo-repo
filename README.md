# EPG Scraper

Automated EPG (Electronic Program Guide) scraper that downloads TV schedule data from XML sources and saves it as JSON files to a GitHub repository.

## Features

- ✅ Downloads and extracts EPG data from `.gz` compressed XML files
- ✅ Supports multiple EPG sources with fallback mechanism
- ✅ Filters schedules for today and tomorrow (Indonesian timezone)
- ✅ Saves channel schedules as organized JSON files
- ✅ Automatic daily updates via GitHub Actions
- ✅ Detailed logging for troubleshooting
- ✅ No external dependencies (uses Python standard library only)

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── epg-scraper.yml       # GitHub Actions workflow
├── schedule/
│   ├── today/                     # Today's schedules
│   │   ├── axn-hd.json
│   │   ├── bloomberg.json
│   │   └── ...
│   └── tomorrow/                  # Tomorrow's schedules
│       ├── axn-hd.json
│       ├── bloomberg.json
│       └── ...
├── epg_scraper.py                 # Main scraper script
├── channel.txt                    # List of channels to scrape
├── scrape.log                     # Latest scrape log
└── README.md
```

## Setup Instructions

### 1. Create a New GitHub Repository

1. Go to [GitHub](https://github.com) and create a new repository
2. Initialize with a README (optional)
3. Clone the repository to your local machine

### 2. Add Files to Repository

Copy these files to your repository:

- `epg_scraper.py` - Main scraper script
- `channel.txt` - Channel list (edit this with your channels)
- `.github/workflows/epg-scraper.yml` - GitHub Actions workflow

**Important:** The workflow file must be placed in `.github/workflows/` directory.

```bash
mkdir -p .github/workflows
mv .github-workflows-epg-scraper.yml .github/workflows/epg-scraper.yml
```

### 3. Configure Channels

Edit `channel.txt` to add the channels you want to scrape:

```text
# Format: channel_id, channel_name
AXN.HD.id, AXN HD
Bloomberg.TV.id, Bloomberg
CNBC.Asia.id, CNBC Asia
```

**Channel Format:**
- Each line contains: `channel_id, channel_name`
- Channel ID should match the ID in the EPG XML
- Channel name is used for the output filename
- Lines starting with `#` are comments

### 4. Add EPG Sources

Edit `epg_scraper.py` to add or modify EPG sources:

```python
EPG_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_ID1.xml.gz",
    # Add more URLs here
    "https://example.com/another-epg-source.xml.gz",
]
```

The script will try the first source, and if a channel is not found, it will try the next source.

### 5. Enable GitHub Actions

1. Go to your repository on GitHub
2. Click on **Settings** → **Actions** → **General**
3. Under "Workflow permissions", select **Read and write permissions**
4. Click **Save**

This allows the GitHub Actions workflow to commit the scraped data back to your repository.

### 6. Test the Workflow

#### Option A: Manual Trigger
1. Go to **Actions** tab in your repository
2. Click on **EPG Scraper** workflow
3. Click **Run workflow** → **Run workflow**
4. Wait for the workflow to complete

#### Option B: Test Locally
```bash
python epg_scraper.py
```

This will create the `schedule/` directory with JSON files and `scrape.log`.

## Usage

### Automatic Daily Updates

The scraper runs automatically every day at **12:10 AM Indonesian Time (WIB)** via GitHub Actions.

The cron schedule is: `10 17 * * *` (5:10 PM UTC = 12:10 AM WIB next day)

### Manual Run

You can manually trigger the scraper:

1. **Via GitHub Actions:**
   - Go to Actions tab → EPG Scraper → Run workflow

2. **Via Command Line:**
   ```bash
   python epg_scraper.py
   ```

### Accessing Schedule Data

After the scraper runs, JSON files are available in:
- `schedule/today/` - Today's schedules
- `schedule/tomorrow/` - Tomorrow's schedules

**Example JSON Output:**
```json
{
  "channel_name": "AXN HD",
  "date": "2026-02-04",
  "programs": [
    {
      "show_name": "Elsbeth",
      "start_time": "00:30:00",
      "end_time": "01:20:00",
      "episode_number": "S2 E2"
    }
  ]
}
```

## Configuration

### Modify Schedule Time

To change when the scraper runs, edit `.github/workflows/epg-scraper.yml`:

```yaml
on:
  schedule:
    - cron: '10 17 * * *'  # Change this line
```

**Cron Time Converter:**
- 12:10 AM WIB = 5:10 PM UTC (previous day) = `10 17 * * *`
- 1:00 AM WIB = 6:00 PM UTC (previous day) = `0 18 * * *`
- 6:00 AM WIB = 11:00 PM UTC (previous day) = `0 23 * * *`

Use [Crontab Guru](https://crontab.guru/) for help with cron syntax.

### Add More EPG Sources

Edit the `EPG_URLS` list in `epg_scraper.py`:

```python
EPG_URLS = [
    "https://source1.com/epg.xml.gz",
    "https://source2.com/epg.xml.gz",
    "https://source3.com/epg.xml.gz",
]
```

The script tries sources in order and uses the first one that has the channel data.

## Logging

The scraper generates a detailed log file: `scrape.log`

**Log Information:**
- Download progress for each EPG source
- Channel matching results
- Number of programs found per channel
- Errors and warnings
- Summary statistics

**View Log:**
- In the repository: Check `scrape.log`
- In GitHub Actions: Download the log artifact from the workflow run

## Troubleshooting

### No channels being scraped

**Check:**
1. Is `channel.txt` formatted correctly?
2. Do the channel IDs match the IDs in the EPG XML?
3. Check `scrape.log` for channel matching details

### Workflow not running automatically

**Check:**
1. Are GitHub Actions enabled in repository settings?
2. Does the workflow have write permissions?
3. Is the cron schedule correct?

### Channel not found

**The script tries to match channels in two ways:**
1. Exact channel ID match
2. Case-insensitive channel name match

**Solutions:**
- Check the EPG XML to find the correct channel ID
- Try using the exact channel name from the EPG
- Check `scrape.log` for available channels

### Empty JSON files

**Possible causes:**
1. No programs scheduled for today/tomorrow
2. Date filtering issue
3. EPG source doesn't have data for those dates

**Check `scrape.log` for:**
- "No programs for today/tomorrow" warnings
- Program count information

## Technical Details

### Time Handling

- EPG XML contains times in format: `20260204003000 +0700`
- The `+0700` indicates Indonesian Time (WIB)
- No timezone conversion needed - times are already in WIB
- Script filters programs by date to separate today/tomorrow

### File Naming

Channel names are converted to lowercase filenames:
- `AXN HD` → `axn-hd.json`
- `Bloomberg TV` → `bloomberg-tv.json`
- Spaces replaced with hyphens
- Special characters removed

### Data Flow

1. Download `.gz` file from EPG source
2. Extract XML content
3. Parse channels and programs
4. Match requested channels from `channel.txt`
5. Filter programs by date (today/tomorrow)
6. Save as JSON files in `schedule/today/` and `schedule/tomorrow/`
7. Commit changes to repository
8. Generate log file

## Python Requirements

**None!** This script uses only Python standard library:
- `gzip` - Decompress .gz files
- `json` - JSON encoding/decoding
- `xml.etree.ElementTree` - XML parsing
- `datetime` - Date/time handling
- `pathlib` - File path operations
- `urllib.request` - HTTP downloads
- `logging` - Logging functionality

## Contributing

Feel free to:
- Add more EPG sources
- Improve channel matching logic
- Add new features
- Report issues

## License

This project is provided as-is for personal use.

## Support

For issues or questions:
1. Check `scrape.log` for detailed error messages
2. Review the troubleshooting section above
3. Check GitHub Actions workflow logs
4. Open an issue in the repository
