"""Command-line interface for asset-scraper."""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.table import Table

from asset_scraper.scraper import MediaScraper


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Download media assets referenced by a web page."
    )
    parser.add_argument("url", help="The web page URL to scrape")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output"),
        help="Directory where assets and scraper.log are stored (default: output)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30)",
    )
    return parser


def configure_logging(log_path: Path) -> None:
    """Configure file logging without writing individual events to the CLI."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG", rotation="10 MB", retention=3)


def display_summary(result: object, output_dir: Path) -> None:
    """Render the download summary table."""
    console = Console()
    table = Table(title="Asset Scrape Summary")
    table.add_column("File extension", style="cyan")
    table.add_column("Downloaded", justify="right", style="green")

    for extension, count in sorted(result.downloaded.items()):
        table.add_row(extension, str(count))
    table.add_row("Failed", str(result.failed), style="red")
    table.add_row("Total discovered", str(result.discovered))

    console.print(table)
    console.print(f"Files saved to: {output_dir.resolve()}")


def main() -> None:
    """Run the command-line scraper."""
    args = build_parser().parse_args()
    configure_logging(args.output / "scraper.log")

    try:
        result = MediaScraper(args.output, timeout=args.timeout).scrape(args.url)
    except Exception as error:
        logger.error("Scrape failed: {}", error)
        raise SystemExit(1) from error

    display_summary(result, args.output)
