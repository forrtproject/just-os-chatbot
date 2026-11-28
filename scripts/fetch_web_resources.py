"""HTML route (issue C3, #18): turn FORRT web resources without a DOI into Markdown.

    docker compose run --rm -v ./data:/app/data web python -m scripts.fetch_web_resources [--sample 50]

Reads the newest eval/results/coverage_*.csv (eval/coverage.py), takes a random sample of
the rows with reason web_page or code_or_osf, downloads each page and keeps its main text.
Output in data/processed/web_markdown/: <hash>.md per page and metadata.csv (doi_hash,
title, link_to_resource, material_type, conditions_of_use), ready for scripts/add_to_index.py.
The licence is unknown, so the bot will not show passages from these pages (issue R5).
"""

import argparse
import csv
import hashlib
import ipaddress
import random
import socket
import urllib.parse
from pathlib import Path
from typing import List, Optional

import httpcore
import httpx
from bs4 import BeautifulSoup

OUT = Path("data/processed/web_markdown")
MIN_CHARS = 500  # shorter pages are menus or landing pages
MAX_BYTES = 5_000_000
DROP = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]


def main_text(html: str) -> str:
    """The readable text of a page: <main> or <article> if present, else <body>, without menus."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(DROP):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = (" ".join(line.split()) for line in root.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


class BlockedURL(ValueError):
    """A link that is not http(s) or points into a private network (SSRF guard)."""


def public_addresses(host: str, port: Optional[int] = None) -> List[str]:
    """The addresses host resolves to, when every one of them is public; else BlockedURL. Links come from sheets and
    the /recommend page, so localhost, the LAN or a cloud metadata address is never fetched."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError) as e:
        raise BlockedURL(f"host not found: {host} ({e})") from e
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise BlockedURL(f"host not found: {host}")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global or ip.is_multicast or getattr(ip, "is_site_local", False):
            raise BlockedURL(f"{host} is a private or local address ({ip})")
    return addresses


def check_http_url(url: str) -> None:
    """Syntactic check only (http/https scheme and host, no DNS lookup)."""
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError as e:
        raise BlockedURL(f"invalid URL: {url!r}") from e
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise BlockedURL(f"not an http(s) link: {url!r}")


def check_public_url(url: str) -> None:
    """Raise BlockedURL unless url is http(s) and every address its host resolves to is public."""
    check_http_url(url)
    parts = urllib.parse.urlsplit(str(url or "").strip())
    public_addresses(parts.hostname, parts.port)


def is_public_url(url: str) -> bool:
    try:
        check_public_url(url)
    except BlockedURL:
        return False
    return True


class BlockedConnect(httpcore.ConnectError):
    """A connection to a private or local address, refused by PublicOnlyBackend; httpx raises it as
    httpx.ConnectError (an httpx.RequestError, so callers that skip a failed source skip it too)."""


class PublicOnlyBackend(httpcore.SyncBackend):
    """The SSRF guard at connection time, for every request and every redirect: resolve the host once, refuse it
    unless all its addresses are public, then connect to the checked address itself, so a DNS answer that changes
    between the check and the connection (DNS rebinding) cannot reach a private address. TLS still verifies the
    certificate against the host name and sends it as SNI (httpcore takes both from the URL, not the socket)."""

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            addresses = public_addresses(host, port)
        except BlockedURL as e:
            raise BlockedConnect(str(e)) from e
        error: Optional[Exception] = None
        for address in addresses:
            try:
                return super().connect_tcp(address, port, timeout=timeout, local_address=local_address,
                                           socket_options=socket_options)
            except httpcore.ConnectError as e:  # the next address of the same host, as socket.create_connection does
                error = e
        raise error

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise BlockedConnect(f"Unix socket {path!r} refused")


class PublicOnlyTransport(httpx.HTTPTransport):
    """httpx transport whose connections go through PublicOnlyBackend. httpx 0.28 has no network_backend argument,
    so the backend is set on the connection pool it builds (test_data_hygiene checks it is in place)."""

    def __init__(self, **kwargs):
        if kwargs.get("proxy") or kwargs.get("uds"):
            raise ValueError("PublicOnlyTransport connects directly: no proxy or Unix socket")
        super().__init__(**kwargs)
        self._pool._network_backend = PublicOnlyBackend()


def public_client(**kwargs) -> httpx.Client:
    """An httpx client that only reaches public addresses (redirects followed, each checked when it connects). An
    explicit transport also turns off proxies from the environment, which would connect for it."""
    return httpx.Client(transport=PublicOnlyTransport(), **{"follow_redirects": True, **kwargs})


def blocked_cause(error: BaseException) -> Optional[BlockedConnect]:
    """The BlockedConnect behind an httpx error, if that is why it failed."""
    while error is not None:
        if isinstance(error, BlockedConnect):
            return error
        error = error.__cause__ or error.__context__
    return None


def fetch(url: str) -> str:
    """The HTML of a public page (at most MAX_BYTES); BlockedURL for a link or redirect to a private address.
    DNS resolution happens once at connect time inside PublicOnlyBackend (no separate preflight lookup)."""
    check_http_url(url)
    try:
        with public_client(timeout=20, headers={"User-Agent": "JUST-OS resource indexer"}) as http:
            with http.stream("GET", url) as response:
                response.raise_for_status()
                if "html" not in response.headers.get("Content-Type", ""):
                    raise ValueError("not an HTML page")
                content = bytearray()
                for chunk in response.iter_bytes():
                    content += chunk
                    if len(content) >= MAX_BYTES:
                        break
                return bytes(content[:MAX_BYTES]).decode(response.charset_encoding or "utf-8", "replace")
    except httpx.HTTPError as e:
        blocked = blocked_cause(e)
        if blocked is not None:
            raise BlockedURL(str(blocked)) from e
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    coverage = sorted(Path("eval/results").glob("coverage_*.csv"))[-1]
    rows = [r for r in csv.DictReader(open(coverage, encoding="utf-8")) if r["reason"] in ("web_page", "code_or_osf")]
    random.Random(args.seed).shuffle(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    kept = []
    for row in rows[: args.sample]:
        url = row["url"].strip()
        try:
            text = main_text(fetch(url))
        except Exception as e:
            print(f"skip {url}: {e}")
            continue
        if len(text) < MIN_CHARS:
            print(f"skip {url}: only {len(text)} characters")
            continue
        key = hashlib.md5(url.encode("utf-8")).hexdigest()
        (OUT / f"{key}.md").write_text(f"# {row['title']}\n\nSource: {url}\n\n{text}\n", encoding="utf-8")
        kept.append({"doi_hash": key, "title": row["title"], "link_to_resource": url,
                     "material_type": row["material_type"], "conditions_of_use": ""})
    with open(OUT / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["doi_hash", "title", "link_to_resource", "material_type", "conditions_of_use"])
        writer.writeheader()
        writer.writerows(kept)
    print(f"{len(kept)} of {min(args.sample, len(rows))} pages kept → {OUT}")
