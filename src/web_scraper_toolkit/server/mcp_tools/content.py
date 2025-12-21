# ./src/web_scraper_toolkit/server/mcp_tools/content.py
"""
Content Processing MCP Tools
=============================

Text chunking, token counting, and text manipulation tools.
"""

import logging

from ...core.content.chunking import chunk_content_simple
from ...core.content.tokens import count_tokens, get_token_info, truncate_to_tokens

logger = logging.getLogger("mcp_server")


def register_content_tools(mcp, create_envelope, format_error, run_in_process):
    """Register content processing tools."""

    @mcp.tool()
    async def chunk_text(
        text: str,
        max_chunk_size: int = 8000,
        overlap: int = 200,
    ) -> str:
        """
        Split text into overlapping chunks for LLM processing.
        Useful for processing content that exceeds context limits.
        """
        try:
            chunks = chunk_content_simple(text, max_chunk_size, overlap)
            return create_envelope(
                "success",
                {"chunks": chunks, "count": len(chunks)},
                meta={"original_length": len(text)},
            )
        except Exception as e:
            return format_error("chunk_text", e)

    @mcp.tool()
    async def get_token_count(text: str, model: str = "default") -> str:
        """
        Estimate token count for text.
        Helps manage LLM context limits.
        """
        try:
            info = get_token_info(text, model)
            return create_envelope("success", info)
        except Exception as e:
            return format_error("get_token_count", e)

    @mcp.tool()
    async def truncate_text(
        text: str,
        max_tokens: int = 8000,
        model: str = "default",
    ) -> str:
        """
        Truncate text to fit within token limit.
        Preserves sentence boundaries when possible.
        """
        try:
            truncated = truncate_to_tokens(text, max_tokens, model)
            return create_envelope(
                "success",
                truncated,
                meta={
                    "original_tokens": count_tokens(text, model),
                    "truncated_tokens": count_tokens(truncated, model),
                },
            )
        except Exception as e:
            return format_error("truncate_text", e)

    logger.info("Registered: content tools (3)")
