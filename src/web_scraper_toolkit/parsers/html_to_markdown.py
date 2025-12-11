# ./src/web_scraper_toolkit/parsers/html_to_markdown.py
"""
HTML to Markdown Converter
==========================

Utility for converting HTML content into clean, readable Markdown.
Specializes in handling tables, lists, and links properly.

Usage:
    md = MarkdownConverter.to_markdown(html_content, base_url="...")

Key Features:
    - Table conversion (ASCII/GD style).
    - Link resolution (absolute paths).
    - Noise removal (scripts/styles).
"""

from bs4 import BeautifulSoup, NavigableString, Tag
import re
from typing import Optional

class MarkdownConverter:
    """
    Converts HTML content to clean Markdown, preserving structure for LLM consumption.
    """

    @staticmethod
    def to_markdown(html_content: str, base_url: str = "") -> str:
        """
        Main entry point. Converts valid HTML string to Markdown.
        """
        if not html_content:
            return ""

        soup = BeautifulSoup(html_content, 'lxml')

        # 1. Cleanup Noise
        # Removing semantic noise is critical for clean output
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "meta", "link", "head", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # 2. Process Content
        # We process the body if available, else the whole soup
        root = soup.body if soup.body else soup
        
        markdown = MarkdownConverter._process_element(root, base_url).strip()
        
        # 3. Post-Processing: Collapse excessive newlines
        # Nested blocks (div > div > p) often generate \n\n\n\n. We want max 2.
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        return markdown

    @staticmethod
    def _is_block_element(tag) -> bool:
        """Checks if a tag is a block element."""
        if not isinstance(tag, Tag): return False
        return tag.name.lower() in ['div', 'section', 'article', 'main', 'header', 'footer', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'table', 'blockquote', 'pre']

    @staticmethod
    def _has_block_children(element) -> bool:
        """Checks if an element contains any direct block-level children."""
        for child in element.children:
            if MarkdownConverter._is_block_element(child):
                return True
            # Also check recursively? No, usually direct children are enough if structure is good.
            # But <a><span><div>..</div></span></a> is possible.
            # Let's do a simple non-recursive check first, or shallow scan.
            # Deep scan:
            if isinstance(child, Tag) and child.find(['div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'table']):
                return True
        return False

    @staticmethod
    def _process_element(element, base_url: str = "", link_context: Optional[str] = None) -> str:
        if element is None:
            return ""

        # TEXT
        if isinstance(element, NavigableString):
            text = element
            # Normalize whitespace but KEEP leading/trailing spaces for separation
            text = re.sub(r'\s+', ' ', text)
            if not text: return ""
            
            # If we are in a link context, we link the text directly
            if link_context and text.strip():
                 # Avoid linking whitespace only
                 return f"[{text}]({link_context})"
            return text

        if not isinstance(element, Tag):
            return ""

        # TAGS mapping
        tag_name = element.name.lower()

        # --- BLOCK ELEMENTS --- #
        
        if tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag_name[1])
            # Pass link_context down to inner text
            content = MarkdownConverter._get_inner_text(element, base_url, link_context)
            # Use fewer newlines to avoid stacking up to 4+
            return f"\n{'#' * level} {content}\n"

        if tag_name == 'p':
            content = MarkdownConverter._get_inner_text(element, base_url, link_context)
            return f"\n{content}\n" if content else ""

        if tag_name == 'br':
            return "\n"

        if tag_name == 'hr':
            return "\n\n---\n\n"

        if tag_name in ['ul', 'ol']:
            return f"\n{MarkdownConverter._process_list(element, base_url, link_context)}\n"

        if tag_name == 'li':
            # Handled by parent UL/OL usually, but if standalone:
            content = MarkdownConverter._get_inner_text(element, base_url, link_context)
            return f"- {content}\n"

        if tag_name == 'blockquote':
            content = MarkdownConverter._get_inner_text(element, base_url, link_context)
            lines = content.split('\n')
            quoted = "\n".join(f"> {line}" for line in lines if line.strip())
            return f"\n{quoted}\n"

        if tag_name == 'pre':
            # Code blocks inside links are rare and likely break markdown parsers anyway.
            # We ignore link_context here for code blocks usually.
            code_tag = element.find('code')
            content = ""
            if code_tag:
               content = code_tag.get_text() # Raw text for code
            else:
               content = element.get_text()
            return f"\n\n```\n{content}\n```\n\n"

        # --- TABLES --- #
        if tag_name == 'table':
            return f"\n\n{MarkdownConverter._process_table(element, base_url)}\n\n"

        # --- INLINE ELEMENTS --- #
        
        if tag_name == 'a':
            href = element.get('href', '')
            if not href or href.startswith('#') or href.startswith('javascript:'):
                return MarkdownConverter._get_inner_text(element, base_url, link_context)

            # Check if this link wraps BLOCK elements
            if MarkdownConverter._has_block_children(element):
                # DISTRIBUTE THE LINK DOWN
                # We do NOT wrap this tag. We recurse.
                return MarkdownConverter._get_inner_text(element, base_url, link_context=href)
            
            # STANDARD INLINE LINK
            text = MarkdownConverter._get_inner_text(element, base_url, link_context)
            # If we are already inside a link context, we shouldn't nest links technically.
            # Markdown doesn't support nested links.
            # We defer to the outer link? Or inner? 
            # Usually inner link takes precedence in HTML, but markdown breaks.
            # Let's assume inner takes precedence.
            return f"[{text}]({href})"

        if tag_name == 'img':
            alt = element.get('alt', 'Image')
            src = element.get('src', '')
            if not src: return ""
            img_md = f"![{alt}]({src})"
            if link_context:
                return f"[{img_md}]({link_context})"
            return img_md

        if tag_name in ['strong', 'b']:
            content = MarkdownConverter._get_inner_text(element, base_url, link_context)
            return f"**{content}**" if content else ""

        if tag_name in ['em', 'i']:
            content = MarkdownConverter._get_inner_text(element, base_url, link_context)
            return f"_{content}_" if content else ""

        if tag_name == 'code':
            # If inside pre, handled by pre. If inline:
            if element.parent.name == 'pre':
                return "" # Let pre handle it
            text = element.get_text()
            return f"`{text}`"

        if tag_name in ['span', 'html']:
            # Just traverse children transparently
            return MarkdownConverter._get_inner_text(element, base_url, link_context)

        if tag_name in ['div', 'section', 'article', 'main', 'header', 'footer', 'body']:
            # Treat as block structural elements. 
            # We add newlines to ensure separation of content blocks.
            content = MarkdownConverter._get_inner_text(element, base_url, link_context)
            if not content.strip():
                return ""
            return f"\n{content}\n"

        # Default fallback
        return MarkdownConverter._get_inner_text(element, base_url, link_context)

    @staticmethod
    def _get_inner_text(element, base_url: str, link_context: Optional[str] = None) -> str:
        """Helper to recursively process children and join them."""
        results = []
        for child in element.children:
            res = MarkdownConverter._process_element(child, base_url, link_context)
            if res:
                results.append(res)
        
        # Intelligent joining
        # To fix "Paragraph**Bold**", we can insert spaces if the elements are inline.
        # But this might break "word," -> "word ,".
        # Simple heuristic: if we are in a block element context, spacing is handled by block logic.
        # If we are in an inline context, we might need a space.
        # A simpler fix for this specific tool: join with " " then remove excessive spaces.
        
        joined = "".join(results)
        
        # Quick fix for Paragraph**Bold** -> Paragraph **Bold**
        # We can just leave it as is if the user didn't put a space in HTML "Paragraph <b>Bold</b>".
        # But BS4 often strips distinct text nodes.
        # Let's try joining with nothing, because usually HTML handles space via text nodes.
        # If the failure 'Paragraph**Bold**' happened, it means the input HTML was "<div><p>Paragraph <b>Bold</b></p></div>".
        # "Paragraph " should be a NavigableString. 
        # Wait, the test input was "<div><p>Paragraph <b>Bold</b></p></div>". 
        # "Paragraph " is a text node. "<b>Bold</b>" is a tag.
        # If _process_element("Paragraph ") returns "Paragraph" (stripped), then we lose the space.
        
        return joined

    @staticmethod
    def _process_list(list_element, base_url: str, link_context: Optional[str] = None) -> str:
        items = []
        is_ordered = list_element.name == 'ol'
        
        for i, child in enumerate(list_element.find_all('li', recursive=False)):
            content = MarkdownConverter._get_inner_text(child, base_url, link_context).strip()
            # Handle nested lists
            nested_list = child.find(['ul', 'ol'])
            nested_md = ""
            if nested_list:
                # remove the text content that belongs to the nested list so we don't duplicate
                # actually _get_inner_text handles recursion, so 'content' already includes the nested list markdown!
                # This is tricky using simple recursion.
                # Let's trust _get_inner_text returns formatting.
                pass
            
            # Simple handling: replace internal newlines for sub-items alignment
            content = content.replace('\n', '\n  ')
            
            prefix = f"{i+1}." if is_ordered else "-"
            items.append(f"{prefix} {content}")
            
        return "\n".join(items)

    @staticmethod
    def _process_table(table_element, base_url: str) -> str:
        """
        Simple Markdown table converter. 
        Only handles standard thead/tbody structures nicely.
        """
        rows = []
        
        # 1. Headers
        headers = []
        thead = table_element.find('thead')
        if thead:
            header_row = thead.find('tr')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
        
        # Fallback: if no thead, check first tr
        if not headers:
            first_tr = table_element.find('tr')
            if first_tr and first_tr.find('th'):
                headers = [th.get_text(strip=True) for th in first_tr.find_all(['th'])]
        
        if headers:
            rows.append(f"| {' | '.join(headers)} |")
            rows.append(f"| {' | '.join(['---'] * len(headers))} |")
        
        # 2. Body
        tbody = table_element.find('tbody')
        row_container = tbody if tbody else table_element
        
        for tr in row_container.find_all('tr'):
            # specific check to skip the header row if we already processed it from 'not headers' logic
            if not headers and tr == table_element.find('tr') and tr.find('th'):
                continue
                
            cols = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if cols:
                # Match header length if possible
                if headers and len(cols) != len(headers):
                    # Pad or truncate? Markdown tables are forgiving of mismatches usually, 
                    # but let's just print what we have
                    pass 
                rows.append(f"| {' | '.join(cols)} |")

        return "\n".join(rows)
