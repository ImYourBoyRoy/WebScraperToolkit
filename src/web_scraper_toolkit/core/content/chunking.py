# ./src/web_scraper_toolkit/core/content/chunking.py
"""
Content Chunking
================

Smart content splitting for LLM context windows.
Supports overlapping chunks for context continuity.

Usage:
    chunks = chunk_content(text, max_size=8000, overlap=200)

Key Features:
    - Paragraph-aware splitting
    - Configurable overlap for context
    - Metadata preservation
    - Skip binary content (PDFs, images)
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class ChunkingConfig:
    """Configuration for content chunking."""

    enabled: bool = False  # Off by default, on-demand
    max_chunk_size: int = 8000  # Characters per chunk
    overlap: int = 200  # Overlap between chunks
    preserve_paragraphs: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkingConfig":
        return cls(
            enabled=data.get("enabled", False),
            max_chunk_size=data.get("max_chunk_size", 8000),
            overlap=data.get("overlap", 200),
            preserve_paragraphs=data.get("preserve_paragraphs", True),
        )


@dataclass
class ContentChunk:
    """Single chunk of content with metadata."""

    content: str
    index: int
    total_chunks: int
    start_char: int
    end_char: int

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "index": self.index,
            "total_chunks": self.total_chunks,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "chunk_size": len(self.content),
        }


def chunk_content(
    content: str,
    max_size: int = 8000,
    overlap: int = 200,
    preserve_paragraphs: bool = True,
) -> List[ContentChunk]:
    """
    Split content into overlapping chunks.

    Args:
        content: Text content to chunk
        max_size: Maximum characters per chunk
        overlap: Number of overlapping characters between chunks
        preserve_paragraphs: Try to split at paragraph boundaries

    Returns:
        List of ContentChunk objects
    """
    if not content or len(content) <= max_size:
        return [
            ContentChunk(
                content=content,
                index=0,
                total_chunks=1,
                start_char=0,
                end_char=len(content),
            )
        ]

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(content):
        end = start + max_size

        # If this is not the last chunk, try to find a good break point
        if end < len(content) and preserve_paragraphs:
            # Look for paragraph break (double newline)
            paragraph_break = content.rfind("\n\n", start + max_size // 2, end)
            if paragraph_break > start:
                end = paragraph_break + 2  # Include the newlines
            else:
                # Look for single newline
                newline_break = content.rfind("\n", start + max_size // 2, end)
                if newline_break > start:
                    end = newline_break + 1
                else:
                    # Look for sentence end
                    sentence_break = max(
                        content.rfind(". ", start + max_size // 2, end),
                        content.rfind("! ", start + max_size // 2, end),
                        content.rfind("? ", start + max_size // 2, end),
                    )
                    if sentence_break > start:
                        end = sentence_break + 2

        # Ensure we don't exceed content length
        end = min(end, len(content))

        chunk_content = content[start:end]
        chunks.append(
            ContentChunk(
                content=chunk_content,
                index=chunk_index,
                total_chunks=0,  # Updated after loop
                start_char=start,
                end_char=end,
            )
        )

        chunk_index += 1

        # Move start position, accounting for overlap
        if end >= len(content):
            break
        start = end - overlap

        # Safety: prevent infinite loop
        if start >= len(content):
            break

    # Update total_chunks in all chunks
    total = len(chunks)
    for chunk in chunks:
        chunk.total_chunks = total

    logger.debug(f"Split content ({len(content)} chars) into {total} chunks")
    return chunks


def chunk_content_simple(
    content: str,
    max_size: int = 8000,
    overlap: int = 200,
) -> List[str]:
    """
    Simple interface returning just content strings.

    Useful for quick integration.
    """
    chunks = chunk_content(content, max_size, overlap)
    return [c.content for c in chunks]


def should_chunk(content: str, max_size: int = 8000) -> bool:
    """Check if content needs chunking."""
    return len(content) > max_size
