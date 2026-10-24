# Local Instagram Unfollower

![Local Instagram Unfollower desktop app](docs/gui.png)

A dead-simple, local app that shows who does **not** follow you back on Instagram.

It reads the official **JSON data export** from Instagram. It does not log in, scrape the website, unfollow anyone automatically, or upload your data anywhere.

## Quick start (Windows)

### 1. Get your Instagram export

1. Open **Instagram Accounts Center**.
2. Go to **Your information and permissions** -> **Download your information**.
3. Choose **Some of your information**.
4. Tick **Followers and following**.
5. Choose **JSON** as the format.
6. Download the ZIP when Instagram says it is ready.

### 2. Download this project

Click **Code -> Download ZIP** on GitHub, then extract the folder somewhere easy, like your Desktop.

### 3. Run it

Double-click **`START_HERE.bat`**.

1. Click **AUTO-FIND MY EXPORT** (it checks Downloads, Desktop and Documents), or pick the ZIP yourself.
2. Click **STEP 3 GENERATE REPORT**.
3. The report opens in your browser.

No terminal, no commands, no Instagram password.

> **Python 3.9 or newer is required.** If the app does not open, install Python from [python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** during setup. Then try `START_HERE.bat` again.

You can also drag your export ZIP directly onto `START_HERE.bat`.

## What it shows

![Report screenshot](docs/report.png)

- **Not following back** - accounts you follow that do not follow you.
- **Fans** - accounts that follow you that you do not follow back.
- **Mutual** - you follow each other.
- **Cleanup progress** - check off accounts as you unfollow them. Progress is saved in your browser.
- **Search, copy, CSV** - find accounts quickly and export the lists.

The report opens Instagram profile links in new tabs. You still click **Unfollow** yourself.

## Privacy

This project contains **no Instagram account data**:

- No export ZIPs, follower lists, usernames from a real account, credentials or local user paths are committed.
- All names in the tests and screenshots are made up.
- Generated reports stay in the local `report/` folder and are excluded by `.gitignore`.
- The app has no analytics, no telemetry, and makes no network requests. The only network activity happens when **you** click a profile link or the Accounts Center help link.

The repository only contains the source code, fake test data and documentation.

## Where the files go

After generating a report, you will find:

```text
report/
  instagram_unfollowers.html
  instagram_unfollowers_not_following_back.txt
  instagram_unfollowers_accounts.csv
```

These files contain your private follower data. Keep them local and do not commit or upload them.

## CLI (optional)

If you prefer the command line:

```powershell
python ig_audit.py "C:\path\to\instagram-export.zip" --open
```

Useful options:

```text
--out PATH    Where to write the HTML report
--open        Open the report when finished
--version     Show the version
```

## macOS / Linux

The GUI works with Python 3.9+ and Tkinter:

```bash
python3 gui.py
```

On some Linux distributions, install Tkinter first:

```bash
sudo apt install python3-tk
```

## Troubleshooting

**`START_HERE.bat` closes immediately**  
Python is probably not installed or is not on `PATH`. Install Python 3.9+ and tick **"Add python.exe to PATH"**.

**Auto-find says no export was found**  
Click **Pick ZIP file** and choose the ZIP manually. Make sure it is the Instagram export, not the email attachment or an unrelated ZIP.

**The counts look wrong**  
Make sure you requested **Followers and following** in **JSON** format. Instagram may split large follower lists into `followers_1.json`, `followers_2.json`, and so on; keep the whole ZIP together so all chunks are read.

**"Could not find the following list"**  
The export was probably HTML instead of JSON. Request a new export and choose JSON.

**Instagram limits or warnings**  
This tool does not unfollow automatically. If you choose to unfollow manually, do it slowly. Rapid bulk actions can trigger Instagram restrictions.

## Development

Run the tests:

```bash
python -m unittest discover -s tests -v
```

The parser supports Instagram's current export format, split follower/following files, ZIP or extracted-folder input, URL-only records, and case-insensitive username matching.

## License

[MIT](LICENSE)
