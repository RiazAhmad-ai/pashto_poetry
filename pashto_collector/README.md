# Pashto Poetry Collector

Local dashboard, link collector, and downloader for the `pashto_poetry` archive folder tree.

The goal of this project is to build a large Pashto poetry research archive. It scans the folder names, understands what kind of data each folder needs, collects useful links first, and downloads actual files only when you enable the downloader.

## Quick Start

Run the local server:

```powershell
cd C:\Users\riaza\Desktop\pashto_poetry
python .\pashto_collector\app.py
```

Open the dashboard:

```text
http://127.0.0.1:8765
```

Recommended first test:

```text
Folder limit: 10
Results per folder: 1
Start links
```

When links start appearing and internet is fast enough:

```text
Start downloads
```

## Main Idea

The collector has two separate phases.

### Phase 1: Link Collection

Use this when internet is slow.

This phase only searches sources and saves links/metadata in:

```text
pashto_collector\data\archive.db
```

It does not download big PDFs, videos, audio files, or images.

### Phase 2: Data Downloads

Use this when internet is fast.

This phase reads saved links from the database and downloads actual data into the matching folder.

For every downloaded file, it also saves a `.source.json` metadata file beside it. That metadata records where the file came from.

Direct files such as PDFs, videos, audio, and images are saved with their real extension. Normal website pages can also be saved as `.html` snapshots when `download_web_pages` is enabled.

## What The Dashboard Shows

The website dashboard shows:

- scanned folder count
- total saved links
- pending downloads
- downloaded links
- metadata-only links
- failed downloads
- local file count
- total downloaded size
- link status chart
- source chart
- link type chart
- local file type chart
- top domains
- discovered websites
- recent links/downloads
- folder-wise downloaded data
- scanned folder requirements and generated queries

## Dashboard Controls

### Folder Limit

How many folders should be processed in one run.

Your archive has thousands of folders, so do not run all folders at once at the start.

Recommended:

```text
Slow internet: 5 to 10
Normal internet: 25 to 50
Fast internet: 100+
```

### Results Per Folder

How many results each source should save per folder query.

Recommended:

```text
Testing: 1
Normal collection: 2 or 3
Deep collection: 5+
```

Actual saved links can be higher because each folder can generate multiple search queries and multiple sources may be enabled.

### Batch Size

How many saved links the downloader should process in one batch.

Recommended:

```text
Slow/unstable internet: 1 to 3
Normal internet: 5
Fast internet: 10+
```

### Keep Waiting For New Links

If enabled, the downloader stays alive and waits for new links. This is useful when link collection and downloads run together.

If disabled, the downloader processes the current queue and stops.

## Best Workflows

### Slow Internet

Use link collection only:

```text
Start links: ON
Start downloads: OFF
Folder limit: 5 or 10
Results per folder: 1
```

This saves source links without downloading big data.

### Fast Internet

Use the downloader:

```text
Start downloads: ON
Batch size: 5 or 10
Keep waiting for new links: ON
```

### Research Mode

Use broader discovery, but avoid big downloads:

```text
Start links: ON
Start downloads: OFF
web_search: true
```

Then review **Discovered Websites** in the dashboard and approve useful domains.

### Full Archive Build

Run in batches:

```text
Folder limit: 50
Results per folder: 2
Start links
```

After each batch, review links and discovered websites. Then increase limits slowly.

## Sources

Sources are configured in:

```text
pashto_collector\config.json
```

Enabled by default:

- Targeted Pashto poetry/literature websites
- Internet Archive
- Open Library
- Wikimedia
- Crossref
- Semantic Scholar
- Library of Congress
- Broad web search discovery

This means the collector is not limited to Internet Archive. It checks known Pashto websites, searches Archive.org, queries free public APIs, and uses broad web search to find other public sources.

Internet Archive may still appear more often at first because the old prototype database already contained Archive links, and Archive.org usually provides cleaner direct download URLs.

## Targeted Websites

The collector has a `targeted_sites` list in `config.json`.

These are important Pashto poetry/literature websites that the system directly checks. It fetches the seed page, extracts same-site links, matches them against folder queries, and saves relevant links.

Example:

```json
{
  "name": "PoetryPashto",
  "url": "https://poetrypashto.com/category/pashto-poetry/"
}
```

To add another website, add a new item to `targeted_sites`:

```json
{
  "name": "My Pashto Source",
  "url": "https://example.com/pashto-poetry"
}
```

Then restart the server.

## Internet Archive

Internet Archive is enabled by default:

```json
"internet_archive": true
```

It searches public Archive.org metadata and saves direct file links when available.

Archive.org is useful because many items expose direct PDF/audio/video download URLs. That makes it easier for the downloader to fetch actual files.

## Free Public APIs

The collector can query several free public APIs. These APIs mostly provide metadata and source links. Some also provide direct open-access PDF/image/file URLs.

Enabled API sources:

- `open_library`: book and author metadata, often linked to Internet Archive items
- `wikimedia`: Pashto/English Wikipedia and Wikimedia Commons pages
- `crossref`: scholarly article/book/chapter DOI metadata
- `semantic_scholar`: academic paper metadata and open-access PDF links when available
- `library_of_congress`: Library of Congress JSON search records and digital resources

Settings:

```json
"public_sources": {
  "open_library": true,
  "wikimedia": true,
  "crossref": true,
  "semantic_scholar": true,
  "library_of_congress": true
}
```

Optional Crossref polite mode:

```json
"api_contact_email": "your-email@example.com"
```

This is optional, but recommended if you run many Crossref requests. Leave it empty if you do not want to provide an email.

Wikimedia projects:

```json
"wikimedia_projects": [
  "ps.wikipedia.org",
  "en.wikipedia.org",
  "commons.wikimedia.org"
]
```

You can add other MediaWiki projects later if needed.

## Broad Web Search

Broad web search is enabled by default:

```json
"web_search": true
```

To reduce noise or save bandwidth, change it to:

```json
"web_search": false
```

Use this carefully. It can find useful sources, but it can also return noisy or irrelevant links.

Recommended when enabling web search:

```text
Folder limit: 5 or 10
Results per folder: 1
Start downloads: OFF
```

When a non-Archive result is a normal web page instead of a direct PDF/audio/video file, the downloader can save it as an `.html` snapshot if this setting is enabled:

```json
"download_web_pages": true
```

With this enabled, non-Archive websites are still useful even when they do not expose direct file links. The saved HTML page keeps the poem/article/source page in the archive, along with `.source.json` metadata.

If you only want direct files and do not want webpage snapshots, set:

```json
"download_web_pages": false
```

## Discovered Websites

When broad discovery finds useful-looking new domains, they appear in the dashboard under **Discovered Websites**.

Each domain can be:

- `candidate`: newly discovered
- `approved`: approved by you for future targeted crawling
- `rejected`: ignored in future review

Use:

```text
Approve
```

for websites that are truly related to Pashto poetry/literature.

Use:

```text
Reject
```

for spam, irrelevant sites, or low-quality sources.

Approved domains are automatically included as targeted sources in future runs.

## Folder Matching

The system reads folder names and infers:

- content type
- topic words
- search queries

Example folder:

```text
02_History_and_Periods/Khattak_Classical_Period/Khushal_Khan_Khattak/Books
```

Possible query:

```text
Pashto poetry Khushal Khan Khattak pdf book article
```

Kinds currently detected:

- `pdf`
- `text`
- `video`
- `lecture`
- `audio`
- `image`
- `other`

## Where Data Is Saved

Downloaded files are saved into the matched project folder.

Example:

```text
00_Collection_Inbox\Books\Some Pashto Book.pdf
00_Collection_Inbox\Books\Some Pashto Book.pdf.source.json
```

For normal web pages:

```text
00_Collection_Inbox\Transcriptions\Some Pashto Poem.html
00_Collection_Inbox\Transcriptions\Some Pashto Poem.html.source.json
```

The `.source.json` file stores:

- title
- source URL
- download URL
- source name
- source ID
- kind
- matched folder
- saved time
- original metadata

## Database

The collector uses SQLite:

```text
pashto_collector\data\archive.db
```

It stores:

- folders
- links
- download states
- events
- candidate domains
- settings

Old `state.json` may still exist from the previous prototype, but the new system uses `archive.db`.

## Config

Important settings in `config.json`:

```json
"default_folder_limit": 25,
"default_results_per_folder": 1,
"default_download_batch_size": 5,
"max_queries_per_folder": 4,
"download_web_pages": true,
"api_contact_email": "",
"request_delay_seconds": 1.0
```

File size limits:

```json
"max_file_mb": {
  "text": 25,
  "pdf": 120,
  "video": 300,
  "lecture": 300,
  "audio": 160,
  "image": 40,
  "other": 40
}
```

Increase these only if you have fast internet and enough disk space.

## Safety Notes

This tool is conservative by design.

- It saves links first.
- It downloads only when the download worker is enabled.
- It respects file size limits.
- It saves metadata beside downloaded files.
- It does not bypass login pages, paywalls, or private access.
- If a direct file is not available, it saves metadata/source link instead.

## Troubleshooting

### Server Does Not Start

Port `8765` may already be in use.

Run on another port:

```powershell
$env:PASHTO_COLLECTOR_PORT="8766"
python .\pashto_collector\app.py
```

Open:

```text
http://127.0.0.1:8766
```

### No Links Found

Try:

```text
Folder limit: 5
Results per folder: 1
```

Then check whether sources are enabled in `config.json`.

For broader discovery, temporarily enable:

```json
"web_search": true
```

### Downloads Are Slow

Turn downloads off and collect links only:

```text
Start links: ON
Start downloads: OFF
```

Later, when internet is fast, run:

```text
Start downloads: ON
```

### Too Many Irrelevant Links

Use lower limits:

```text
Folder limit: 5
Results per folder: 1
```

If broad search is too noisy, temporarily set:

```json
"web_search": false
```

Reject bad domains in **Discovered Websites**.

If you only want direct files and not `.html` webpage snapshots, set:

```json
"download_web_pages": false
```

### Downloads Fail

Common reasons:

- source blocks direct download
- file is too large
- link expired
- internet dropped
- website requires login
- server returned 401, 403, 404, or timeout

Failed links stay in the database as `download_failed`.

## Recommended First Run

1. Start the app.
2. Open the dashboard.
3. Set:

```text
Folder limit: 10
Results per folder: 1
```

4. Click:

```text
Start links
```

5. Wait for links to appear.
6. Review **Recent Links And Downloads**.
7. Review **Discovered Websites**.
8. Approve useful domains.
9. When internet is fast, click:

```text
Start downloads
```

## File Structure

```text
pashto_collector/
  app.py
  config.json
  README.md
  collector/
    queries.py
    scanner.py
  downloader/
    downloader.py
  sources/
    crossref.py
    internet_archive.py
    library_of_congress.py
    open_library.py
    semantic_scholar.py
    targeted_sites.py
    web_search.py
    wikimedia.py
  storage/
    database.py
  static/
    index.html
    app.js
    styles.css
  data/
    archive.db
```

## Current Development Direction

The system is designed so more source connectors can be added later, for example:

- YouTube metadata/link collector
- Open Library connector
- university journal connector
- PDF repository connector
- Pashto books website connector
- sitemap crawler
- RSS/feed crawler
- duplicate file hashing
- better Pashto-script query generation
- manual review queue
