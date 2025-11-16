# Plex Music Timestamp Fixer for MacOS

A Python utility for repairing incorrect **Date Added** metadata in Plex music libraries. Plex occasionally applies future timestamps to tracks or their parent albums, which causes them to appear incorrectly in the **Recently Added** carousel even when they were added months or years earlier.

This tool reads the **true file creation time** from the filesystem and uses it to correct Plex’s internal metadata, ensuring Plex sorts music items accurately.

## What it fixes

- Tracks with incorrect `added_at` dates  
- Parent albums with inconsistent `added_at` and `created_at` values  
- Future-dated items that show up incorrectly in “Recently Added”  
- Tracks where Plex ignored the actual file timestamp during import  

## How it works

- Reads Plex’s `metadata_items` and `media_parts` tables  
- Extracts the **Date Created** value from each media file  
- Updates both:
  - `added_at`
  - `created_at`  
- Writes changes **safely using Plex’s bundled SQLite engine**  
- Supports:
  - Fixing a single track by ID  
  - Bulk repair of all tracks with future `added_at` timestamps  

## Requirements

- macOS  
- Plex Media Server installed locally  
- Python 3  
- Plex Media Server **must be stopped** before running  
- Always back up `com.plexapp.plugins.library.db` before making changes  

## Usage

```bash
python3 update_plex_timestamp.py
```

Choose between:
1. Fix a single track by providing a metadata item ID
2. Bulk-fix all future-dated tracks and their parent albums

The script shows a full summary before applying changes and requires confirmation.
