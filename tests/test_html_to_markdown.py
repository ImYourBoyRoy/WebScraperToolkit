import unittest
import sys
import os
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from web_scraper_toolkit.parsers.html_to_markdown import MarkdownConverter


class TestMarkdownConverter(unittest.TestCase):
    def setUp(self):
        # Cache Scrub (Roy-Standard)
        import shutil

        cache_path = os.path.join(os.path.dirname(__file__), "__pycache__")
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
            except:
                pass

    def test_basic_conversion(self):
        html = "<h1>Title</h1><p>Body text.</p>"
        expected = "\n\n# Title\n\n\n\nBody text.\n\n"
        # We strip to avoid whitespace nitpicking on exact newlines
        self.assertEqual(
            MarkdownConverter.to_markdown(html).strip(), "# Title\n\nBody text."
        )

    def test_links(self):
        html = '<a href="https://example.com">Example</a>'
        expected = "[Example](https://example.com)"
        self.assertEqual(MarkdownConverter.to_markdown(html).strip(), expected)

    def test_lists(self):
        html = """
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
        """
        # Expected:
        # - Item 1
        # - Item 2
        md = MarkdownConverter.to_markdown(html).strip()
        self.assertIn("- Item 1", md)
        self.assertIn("- Item 2", md)

    def test_nested_structure(self):
        html = "<div><p>Paragraph <b>Bold</b></p></div>"
        md = MarkdownConverter.to_markdown(html).strip()
        self.assertEqual(md, "Paragraph **Bold**")

    def test_tables(self):
        html = """
        <table>
            <thead>
                <tr><th>Header 1</th><th>Header 2</th></tr>
            </thead>
            <tbody>
                <tr><td>Row 1 Col 1</td><td>Row 1 Col 2</td></tr>
            </tbody>
        </table>
        """
        md = MarkdownConverter.to_markdown(html).strip()
        self.assertIn("| Header 1 | Header 2 |", md)
        self.assertIn("| --- | --- |", md)
        self.assertIn("| Row 1 Col 1 | Row 1 Col 2 |", md)

    def test_noise_removal(self):
        html = "<p>Text</p><script>console.log('bad')</script><style>css</style>"
        md = MarkdownConverter.to_markdown(html).strip()
        self.assertEqual(md, "Text")

    def test_div_separation(self):
        html = "<div>Line 1</div><div>Line 2</div>"
        md = MarkdownConverter.to_markdown(html).strip()
        cleaned = re.sub(r"\n+", "\n", md)
        self.assertEqual(cleaned, "Line 1\nLine 2")

    def test_block_link_distribution(self):
        # Case A: Complex link with Header and Text
        html = '<a href="/test"><h3>Header</h3><p>Content</p></a>'
        md = MarkdownConverter.to_markdown(html).strip()

        # We expect distribution:
        # ### [Header](/test)
        # [Content](/test)

        self.assertIn("### [Header](/test)", md)
        self.assertIn("[Content](/test)", md)
        self.assertFalse("[ ### Header" in md)  # Should NOT wrap the block markers

        # Case B: Image inside link
        html = '<a href="/img"><img src="pic.jpg" alt="Alt"></a>'
        md = MarkdownConverter.to_markdown(html).strip()
        self.assertEqual(md, "[![Alt](pic.jpg)](/img)")


if __name__ == "__main__":
    unittest.main()
