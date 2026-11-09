import os
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Union

import pandas as pd
from dotenv import load_dotenv
import difflib
import hashlib

import concurrent.futures
from tqdm import tqdm

import logging

from just_os.references import normalize_doi

# Configuration
load_dotenv()
EMAIL = os.environ.get("UNPAYWALL_EMAIL", "")
UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"
# List of URLs that will be combined
URL_FORRT = [
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRgYcUP3ybhe4x05Xp4-GTf-Cn2snBCW8WOP_N7X-9r80AeCpFAGTfWn6ITtBk-haBkDqXAYXh9a_x4/pub?gid=1924034107&single=true&output=csv",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vQy-x6byM-pT1j_Fa8RnKrR-XJS0nbrdrmqP8c9-BVGzWdcL7znJt0XmAOocHMe-bgrAD7TcLyF3o46/pub?gid=0&single=true&output=csv"
]



def execute_concurrent_tasks(
    items, task_function, total_desc="Processing items", max_workers=5
):
    """
    Execute tasks concurrently using ThreadPoolExecutor

    Args:
        task_function: Function that takes item as argument
        total_desc: Description for tqdm progress bar
        max_workers: Maximum number of worker threads

    Returns:
        Dictionary mapping indices to results
    """
    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(task_function, item): i for i, item in items}

        for future in tqdm(
            concurrent.futures.as_completed(future_to_idx),
            total=len(future_to_idx),
            desc=total_desc,
        ):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results[idx] = result
            except Exception as e:
                logging.error(f"Error processing item at index {idx}: {str(e)}")
                continue

    return results


# Network utilities
def load_url(url: str) -> bytes:
    """Load data from a URL and return the raw bytes."""
    with urllib.request.urlopen(url) as conn:
        return conn.read().decode("utf-8")


def import_data(url: str) -> pd.DataFrame:
    """Import CSV data from a URL into a pandas DataFrame."""
    return pd.read_csv(url)


def get_unpaywall_info_by_doi(doi: str) -> bytes:
    """Fetch information about a DOI from the Unpaywall API."""
    url = f"{UNPAYWALL_API_BASE}/{doi}?email={EMAIL}"
    return load_url(url)


def get_unpaywall_info_by_title(title: str) -> bytes:
    params = urllib.parse.urlencode({"query": title, "email": EMAIL})
    url = f"{UNPAYWALL_API_BASE}/search?{params}"
    return load_url(url)


def download_and_save_pdf(pdf_url: str, doi: str, output_dir: Path) -> str:
    """Download a PDF from a URL and save it to disk.

    Args:
        pdf_url: The URL of the PDF to download
        doi: The DOI associated with the PDF
        output_dir: The directory to save the PDF in

    Returns:
        The filename of the saved PDF
    """
    hash_filename = f"{hashlib.md5(doi.encode()).hexdigest()}.pdf"

    try:
        with urllib.request.urlopen(pdf_url, timeout=60) as response:
            content = response.read()
    except Exception as e:
        logging.error(f"Error downloading PDF at url {pdf_url}: {str(e)}")
        return None

    # Landing pages and paywalls answer with HTML; keep only real PDFs
    if not content.startswith(b"%PDF"):
        logging.error(f"Not a PDF at url {pdf_url}")
        return None

    output_dir.joinpath(hash_filename).write_bytes(content)
    return hash_filename


def _plain(title) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(title or "").lower()))


def best_title_match(title: str, results: list, min_ratio: float = 0.9):
    """First Unpaywall search result whose title is close enough to `title`, else None.

    The search ranks by relevance, so its first result can be a different paper.
    """
    wanted = _plain(title)
    for result in results or []:
        response = result.get("response") or {}
        found = _plain(response.get("title"))
        if wanted and found and difflib.SequenceMatcher(None, wanted, found).ratio() >= min_ratio:
            return response
    return None


# Data extraction utilities
def get_doi_from_url(url: str) -> Union[str, None]:
    """Extract a DOI from a URL if present."""
    return normalize_doi(url)


def wrangle_data_forrt(df):
    """
    Standardize column names
    """
    df.columns = df.columns.str.lower()
    df.rename(
        columns={
            df.columns[df.columns.str.contains(pat="provider")][0]: "creators",
            df.columns[df.columns.str.contains(pat="url")][0]: "link_to_resource",
            df.columns[df.columns.str.contains(pat="material type")][
                0
            ]: "material_type",
            df.columns[df.columns.str.contains(pat="education level")][
                0
            ]: "education_level",
            df.columns[df.columns.str.contains(pat="conditions of use")][
                0
            ]: "conditions_of_use",
            df.columns[df.columns.str.contains(pat="primary user")][0]: "primary_user",
            df.columns[df.columns.str.contains(pat="subject areas")][
                0
            ]: "subject_areas",
            df.columns[df.columns.str.contains(pat="clusters")][0]: "FORRT_clusters",
            df.columns[df.columns.str.contains(pat="user tags")][0]: "tags",
        },
        inplace=True,
    )
    df.fillna("", inplace=True)
    return df


# Data transformation utilities
def wrangle_data_justos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize column names in the DataFrame.

    Args:
        df: Input DataFrame with inconsistent column names

    Returns:
        DataFrame with standardized column names
    """
    df.columns = df.columns.str.lower()

    rename_dict = {
        df.columns[df.columns.str.contains(pat="provider")][0]: "creators",
        df.columns[df.columns.str.contains(pat="url")][0]: "link_to_resource",
        df.columns[df.columns.str.contains(pat="material type")][0]: "material_type",
        df.columns[df.columns.str.contains(pat="education level")][
            0
        ]: "education_level",
        df.columns[df.columns.str.contains(pat="conditions of use")][
            0
        ]: "conditions_of_use",
        df.columns[df.columns.str.contains(pat="primary user")][0]: "primary_user",
        df.columns[df.columns.str.contains(pat="subject areas")][0]: "subject_areas",
        df.columns[df.columns.str.contains(pat="clusters")][0]: "FORRT_clusters",
        df.columns[df.columns.str.contains(pat="user tags")][0]: "tags",
        df.columns[df.columns.str.contains(pat="just-os internal identifier")][
            0
        ]: "just_os_id",
        df.columns[df.columns.str.contains(pat="downloaded?")][0]: "is_downloaded",
    }

    df.rename(
        columns=rename_dict,
        inplace=True,
    )

    selected_columns = ["title", "timestamp"] + list(rename_dict.values())

    df.fillna("", inplace=True)
    return df[selected_columns]


def split_cells(df: pd.DataFrame) -> pd.DataFrame:
    """
    Split comma-separated values in cells into lists.

    Args:
        df: DataFrame with comma-separated string values

    Returns:
        DataFrame with lists instead of comma-separated strings
    """
    columns_to_split = [
        "creators",
        "primary_user",
        "material_type",
        "education_level",
        "subject_areas",
        "FORRT_clusters",
        "tags",
        "language",
    ]

    for column in columns_to_split:
        if column in df.columns:
            df[column] = [[y.strip() for y in x.split(",")] for x in df[column].values]

    return df
