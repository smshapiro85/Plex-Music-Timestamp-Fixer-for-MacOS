import os
import sys
import time
import sqlite3
import subprocess

PLEX_SQLITE = "/Applications/Plex Media Server.app/Contents/MacOS/Plex SQLite"
DB_PATH = os.path.expanduser(
    "~/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db"
)


def human(ts):
    return "None" if ts is None else time.ctime(ts)


def ensure_paths():
    if not os.path.isfile(PLEX_SQLITE):
        print(f"ERROR: Plex SQLite not found at:\n  {PLEX_SQLITE}")
        sys.exit(1)
    if not os.path.isfile(DB_PATH):
        print(f"ERROR: Plex DB not found at:\n  {DB_PATH}")
        sys.exit(1)


def get_creation_ts_for_track(cur, track_id):
    cur.execute(
        """
        SELECT mp.file
        FROM media_items mii
        JOIN media_parts mp ON mp.media_item_id = mii.id
        WHERE mii.metadata_item_id = ?
        """,
        (track_id,),
    )
    paths = [r[0] for r in cur.fetchall()]
    if not paths:
        return None, []

    creation_times = []
    for p in paths:
        if os.path.exists(p):
            creation_times.append(os.path.getctime(p))

    if not creation_times:
        return None, paths

    return int(min(creation_times)), paths


def run_plex_sql(sql):
    result = subprocess.run(
        [PLEX_SQLITE, DB_PATH, sql],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print("\nERROR running Plex SQLite.")
        print("stdout:")
        print(result.stdout)
        print("stderr:")
        print(result.stderr)
        sys.exit(1)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())


def fix_single():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    meta_id_raw = input("Enter TRACK metadata_items.id to inspect/update: ").strip()
    if not meta_id_raw.isdigit():
        print("Invalid id. Must be a number.")
        return
    track_id = int(meta_id_raw)

    cur.execute(
        "SELECT title, added_at, created_at, parent_id FROM metadata_items WHERE id = ?",
        (track_id,),
    )
    row = cur.fetchone()
    if not row:
        print(f"No metadata_items row found for id {track_id}")
        conn.close()
        return

    track_title, track_added_at, track_created_at, parent_id = row

    parent_title = parent_added_at = parent_created_at = None
    if parent_id is not None:
        cur.execute(
            "SELECT title, added_at, created_at FROM metadata_items WHERE id = ?",
            (parent_id,),
        )
        prow = cur.fetchone()
        if prow:
            parent_title, parent_added_at, parent_created_at = prow

    new_ts, paths = get_creation_ts_for_track(cur, track_id)
    print("\nFiles and Date Created:")
    for p in paths:
        print(f"  {p}")
        if os.path.exists(p):
            ctime = os.path.getctime(p)
            print(f"    created_at: {ctime} ({human(ctime)})")
        else:
            print("    [WARNING] File does not exist.")

    if new_ts is None:
        print("No usable creation times found.")
        conn.close()
        return

    print("\nSummary (proposed new timestamp from file Date Created):")
    print(f"New timestamp: {new_ts} ({human(new_ts)})\n")

    print("Track (child):")
    print(f"  id:         {track_id}")
    print(f"  title:      {track_title}")
    print(f"  added_at:   {track_added_at} ({human(track_added_at)})")
    print(f"  created_at: {track_created_at} ({human(track_created_at)})\n")

    if parent_id is not None and parent_title is not None:
        print("Parent (album):")
        print(f"  id:         {parent_id}")
        print(f"  title:      {parent_title}")
        print(f"  added_at:   {parent_added_at} ({human(parent_added_at)})")
        print(f"  created_at: {parent_created_at} ({human(parent_created_at)})")
    else:
        print("No parent metadata_item found; only the track will be updated.")

    conn.close()

    confirm = input("\nUpdate TRACK and PARENT added_at + created_at to this value? [Y/N]: ").strip().upper()
    if confirm != "Y":
        print("Cancelled. No changes made.")
        return

    statements = [
        f"UPDATE metadata_items SET added_at = {new_ts}, created_at = {new_ts} WHERE id = {track_id}"
    ]
    if parent_id is not None and parent_title is not None:
        statements.append(
            f"UPDATE metadata_items SET added_at = {new_ts}, created_at = {new_ts} WHERE id = {parent_id}"
        )

    sql = "BEGIN; " + "; ".join(statements) + "; COMMIT;"
    print("\nRunning via Plex SQLite:")
    print(f"  {sql}")
    run_plex_sql(sql)
    print("\nUpdate complete.")
    print(f"Track id={track_id} and parent id={parent_id} (if present) now have:")
    print(f"  added_at = {new_ts} ({human(new_ts)})")
    print(f"  created_at = {new_ts} ({human(new_ts)})")


def fix_bulk_future():
    now_ts = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # metadata_type = 10 for tracks
    cur.execute(
        """
        SELECT id, title, added_at, parent_id
        FROM metadata_items
        WHERE metadata_type = 10
          AND added_at IS NOT NULL
          AND added_at > ?
        """,
        (now_ts,),
    )
    rows = cur.fetchall()
    if not rows:
        print("No future-dated tracks found.")
        conn.close()
        return

    print(f"Found {len(rows)} future-dated tracks.\n")

    tracks_to_fix = []
    parent_min_ts = {}

    for track_id, title, added_at, parent_id in rows:
        new_ts, paths = get_creation_ts_for_track(cur, track_id)
        if new_ts is None:
            print(f"[SKIP] Track id={track_id} '{title}' has no usable file creation time.")
            continue

        tracks_to_fix.append((track_id, new_ts))

        if parent_id is not None:
            if parent_id not in parent_min_ts or new_ts < parent_min_ts[parent_id]:
                parent_min_ts[parent_id] = new_ts

    conn.close()

    if not tracks_to_fix:
        print("Nothing to update after checking filesystem timestamps.")
        return

    print("Summary of planned updates:")
    print(f"  Tracks to fix:  {len(tracks_to_fix)}")
    print(f"  Parents to fix: {len(parent_min_ts)}")
    print(f"  Example new timestamp: {tracks_to_fix[0][1]} ({human(tracks_to_fix[0][1])})")

    confirm = input("\nProceed with bulk update of all these items? [Y/N]: ").strip().upper()
    if confirm != "Y":
        print("Cancelled. No changes made.")
        return

    statements = []
    for track_id, ts in tracks_to_fix:
        statements.append(
            f"UPDATE metadata_items SET added_at = {ts}, created_at = {ts} WHERE id = {track_id}"
        )
    for parent_id, ts in parent_min_ts.items():
        statements.append(
            f"UPDATE metadata_items SET added_at = {ts}, created_at = {ts} WHERE id = {parent_id}"
        )

    sql = "BEGIN; " + "; ".join(statements) + "; COMMIT;"
    print("\nRunning via Plex SQLite:")
    print(f"  {sql[:500]}..." if len(sql) > 500 else f"  {sql}")

    run_plex_sql(sql)

    print("\nBulk update complete.")
    print(f"  Tracks updated:  {len(tracks_to_fix)}")
    print(f"  Parents updated: {len(parent_min_ts)}")


def main():
    ensure_paths()

    print("Choose mode:")
    print("  1) Fix a single track by metadata_items.id")
    print("  2) Bulk fix all tracks with future added_at values")
    mode = input("Enter 1 or 2: ").strip()

    if mode == "1":
        fix_single()
    elif mode == "2":
        fix_bulk_future()
    else:
        print("Invalid choice. Exiting.")


if __name__ == "__main__":
    main()