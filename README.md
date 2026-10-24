# Local Instagram Unfollower

A local, read-only tool that compares your Instagram followers and following lists from a data export and shows who doesn't follow you back. No login, no scraping, no automatic unfollowing.

## Features

- **Local only** - Everything runs on your machine. No credentials or data leave it.
- **Handles real exports** - Reads JSON from Instagram's "Download your information" export, including split `followers_*.json` files and ZIPs.
- **Clear categories** - Not following back, fans (follow you, you don't follow them), and mutual follows.
- **Manual workflow** - Profile links, "Open next" button, check-off tracking saved in your browser.
- **Exportable** - Copy usernames or download CSV.
- **Tested** - Parser covered by unit tests, works with large exports.

## Get your Instagram export

1. Go to [Instagram Accounts Center](https://accountscenter.instagram.com/) → **Your info and permissions** → **Download your info**.
2. Select **Download or transfer info** → your Instagram profile.
3. Select **Some of your info** → check **Followers and following**.
4. Select **JSON** format and choose a date range (e.g., **All time**).
5. Create export. You'll get an email when it's ready; download the ZIP.

## Usage

### Option 1: Drag and drop (Windows)
Drag the downloaded ZIP onto `run_audit.bat`. It will generate a report and open it in your browser.

### Option 2: Command line
Requires Python 3.9+ (no external dependencies).

```bash
python ig_audit.py "path/to/instagram-export.zip"
```

Or with an extracted folder:
```bash
python ig_audit.py "path/to/extracted-export" --out report.html --open
```

### Outputs
- `instagram_audit.html` - Interactive dashboard
- `instagram_audit_not_following_back.txt` - Usernames (one per line)
- `instagram_audit_accounts.csv` - All accounts with timestamps and categories

## Safety notes

- **Manual unfollowing only** - This tool never unfollows anyone for you.
- **Respect rate limits** - If you unfollow manually, do it slowly to avoid restrictions.
- **Keep exports private** - They contain your follower lists; don't share them.

## Development

```bash
python -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)
