# ./src/web_scraper_toolkit/core/file_utils.py
"""
File Utilities
==============

Provides helper functions for file system operations, path safety, and content merging.

Usage:
    safe_name = generate_safe_filename("invalid/name")
    ensure_directory("path/to/dir")

Key Functions:
    - ensure_directory: Creates dir if not exists.
    - generate_safe_filename: Sanitizes strings for FS.
    - merge_content_files: Combines split outputs.
"""

import os
import re
import hashlib
import logging
from urllib.parse import urlparse
from typing import List, Optional

logger = logging.getLogger(__name__)

def ensure_directory(path: str):
    """Ensure directory exists, create if not."""
    if path and path != "." and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        logger.info(f"Created directory: {path}")

def generate_safe_filename(url: str, output_dir: str, extension: str, specific_name: Optional[str] = None) -> str:
    """
    Generate a safe, unique filename or use specific name if provided.
    Always joins with output_dir.
    """
    if specific_name:
        return os.path.join(output_dir, specific_name)

    domain = urlparse(url).netloc.replace("www.", "")
    safe_name = "".join(x for x in domain if x.isalnum() or x in "._-")
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    filename = f"{safe_name}_{url_hash}.{extension.lstrip('.')}"
    
    return os.path.join(output_dir, filename)

def get_unique_filepath(base_path: str) -> str:
    """
    Returns a unique filepath by appending a counter if the file already exists.
    e.g. output.pdf -> output_1.pdf -> output_2.pdf
    """
    if not os.path.exists(base_path):
        return base_path

    directory, filename = os.path.split(base_path)
    name, ext = os.path.splitext(filename)
    counter = 1

    while True:
        new_name = f"{name}_{counter}{ext}"
        new_path = os.path.join(directory, new_name)
        if not os.path.exists(new_path):
            return new_path
        counter += 1

def merge_content_files(outputs: List[str], format_type: str, output_filename: str):
    """Merge collected outputs into a single file."""
    if not outputs: return

    if format_type == 'pdf':
        try:
            from pypdf import PdfWriter
            merger = PdfWriter()
            for pdf_file in outputs:
                if os.path.exists(pdf_file):
                    merger.append(pdf_file)
            
            with open(output_filename, "wb") as f_out:
                merger.write(f_out)
            logger.info(f"Merged PDF saved to {output_filename}")
        except ImportError:
            logger.error("pypdf not installed. Cannot merge PDFs.")
        except Exception as e:
            logger.error(f"Error merging PDFs: {e}")

    else:
        # Text/Markdown/HTML merge
        with open(output_filename, "w", encoding="utf-8") as f:
            for i, content in enumerate(outputs):
                f.write(f"\n\n=== SOURCE {i+1} ===\n\n")
                f.write(content)
                f.write(f"\n\n=== END SOURCE {i+1} ===\n\n")
        logger.info(f"Merged content saved to {output_filename}")
