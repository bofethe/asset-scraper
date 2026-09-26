# Asset Scraper

Download media referenced by a web page into folders organized by file
extension. The scraper supports images, video, audio, fonts and other media
references found in HTML attributes and CSS `url(...)` declarations.

## Usage

This project uses [uv](https://docs.astral.sh/uv/) to build and manage a python virtual environment. Once you have that installed, open the asset-scraper directory in a terminal and install the dependencies. This also refreshes your environment if you recently pulled an update from GitHub.

```bash
uv sync
```

Then run your first process:

```bash
uv run asset-scraper https://example.com
```

By default, files are written to `output/`:

```text
output/
├── jpg/
├── mp4/
├── png/
└── scraper.log
```

Use a different output directory or HTTP timeout when needed:

```bash
uv run asset-scraper https://example.com --output downloads --timeout 60
```

The command prints a summary table grouped by extension. Detailed logs are
written to `output/scraper.log` and progress is also shown in the terminal.

## Development

View all available CLI arguments

```bash
uv run asset-scraper --help
```
