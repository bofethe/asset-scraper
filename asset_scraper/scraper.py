"""Core media discovery and download functionality."""

from __future__ import annotations

import mimetypes
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

MEDIA_ATTRIBUTES = (
    ("img", "src"),
    ("img", "data-src"),
    ("img", "srcset"),
    ("source", "src"),
    ("source", "srcset"),
    ("video", "poster"),
    ("video", "src"),
    ("audio", "src"),
    ("track", "src"),
    ("embed", "src"),
    ("object", "data"),
    ("link", "href"),
)
CSS_URL_PATTERN = re.compile(r"url\(\s*[\"']?([^\"')]+)")
SCRIPT_MEDIA_PATTERN = re.compile(
    r"(?:https?://[^\"'\s]+/)?static/media/[A-Za-z0-9._-]+"
)
SUPPORTED_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".ogv",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".wav",
    ".webm",
    ".webp",
}


@dataclass(frozen=True)
class ScrapeResult:
    """The outcome of scraping one page."""

    downloaded: Counter[str]
    failed: int
    discovered: int


class MediaScraper:
    """Discover and download media assets referenced by one web page."""

    def __init__(self, output_dir: Path, timeout: float = 30.0) -> None:
        self.output_dir = output_dir
        self.timeout = timeout
        self._used_names: set[Path] = set()

    def scrape(self, page_url: str) -> ScrapeResult:
        """Download media assets found at ``page_url``."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        downloaded: Counter[str] = Counter()
        failed = 0

        with httpx.Client(
            follow_redirects=True,
            timeout=self.timeout,
            headers={"User-Agent": "asset-scraper"},
        ) as client:
            response = client.get(page_url)
            response.raise_for_status()
            media_urls = discover_media_urls(response.text, page_url)
            media_urls.extend(
                discover_script_media_urls(response.text, page_url, client)
            )
            media_urls = list(dict.fromkeys(media_urls))
            logger.info("Discovered {} media URLs on {}", len(media_urls), page_url)

            for media_url in media_urls:
                try:
                    extension = self._download(client, media_url)
                    downloaded[extension] += 1
                except (httpx.HTTPError, OSError, ValueError) as error:
                    failed += 1
                    logger.warning("Could not download {}: {}", media_url, error)

        logger.info(
            "Scrape complete: {} downloaded, {} failed",
            sum(downloaded.values()),
            failed,
        )
        return ScrapeResult(downloaded, failed, len(media_urls))

    def _download(self, client: httpx.Client, media_url: str) -> str:
        response = client.get(media_url)
        response.raise_for_status()
        if not response.content:
            raise ValueError("response contained no data")

        extension = extension_for(media_url, response.headers.get("content-type", ""))
        destination_dir = self.output_dir / extension.lstrip(".")
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = unique_destination(destination_dir, media_url, extension)
        destination.write_bytes(response.content)
        self._used_names.add(destination)
        logger.info("Downloaded {} -> {}", media_url, destination)
        return extension


def discover_media_urls(html: str, page_url: str) -> list[str]:
    """Return unique media URLs referenced by HTML and inline CSS."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []

    for tag_name, attribute in MEDIA_ATTRIBUTES:
        for tag in soup.find_all(tag_name):
            value = tag.get(attribute)
            if not value:
                continue
            values = value.split(",") if attribute == "srcset" else [value]
            candidates.extend(item.strip().split(" ", 1)[0] for item in values)

    for style in soup.find_all(style=True):
        candidates.extend(CSS_URL_PATTERN.findall(style["style"]))
    for style_tag in soup.find_all("style"):
        candidates.extend(CSS_URL_PATTERN.findall(style_tag.get_text()))

    resolved_urls = (urljoin(page_url, url) for url in candidates)
    return list(
        dict.fromkeys(
            normalize_url(url) for url in resolved_urls if is_http_url(url)
        )
    )


def discover_script_media_urls(
    html: str, page_url: str, client: httpx.Client
) -> list[str]:
    """Return media URLs embedded in same-page JavaScript bundles."""
    soup = BeautifulSoup(html, "html.parser")
    script_urls = [
        urljoin(page_url, script["src"])
        for script in soup.find_all("script", src=True)
    ]
    candidates: list[str] = []

    for script_url in script_urls:
        try:
            response = client.get(script_url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            logger.debug("Could not inspect script {}: {}", script_url, error)
            continue
        candidates.extend(SCRIPT_MEDIA_PATTERN.findall(response.text))

    return list(
        dict.fromkeys(
            normalize_url(urljoin(page_url, url))
            for url in candidates
            if is_http_url(urljoin(page_url, url))
        )
    )


def normalize_url(url: str) -> str:
    """Remove fragments, which do not change the downloaded resource."""
    return urldefrag(url)[0]


def is_http_url(url: str) -> bool:
    """Return whether a URL can be fetched over HTTP(S)."""
    return urlparse(url).scheme in {"http", "https"}


def extension_for(url: str, content_type: str) -> str:
    """Determine a lowercase file extension from URL or response metadata."""
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return suffix

    media_type = content_type.split(";", 1)[0].strip().lower()
    guessed = mimetypes.guess_extension(media_type) or ".bin"
    return ".jpg" if media_type == "image/jpg" else guessed


def unique_destination(directory: Path, url: str, extension: str) -> Path:
    """Create a readable, collision-free destination path."""
    name = Path(urlparse(url).path).stem or "asset"
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._") or "asset"
    destination = directory / f"{safe_name}{extension}"
    counter = 2
    while destination.exists():
        destination = directory / f"{safe_name}_{counter}{extension}"
        counter += 1
    return destination
