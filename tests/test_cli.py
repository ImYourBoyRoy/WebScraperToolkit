
import unittest
from unittest.mock import MagicMock, patch, AsyncMock, Mock
import sys
import os
import argparse

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from web_scraper_toolkit import cli

class TestCLI(unittest.TestCase):
    
    def setUp(self):
        # Silence the rich console
        patcher = patch('web_scraper_toolkit.cli.console', Mock())
        self.mock_console = patcher.start()
        self.addCleanup(patcher.stop)

    def test_argument_parser(self):
        # Test default args
        parser = cli.parse_arguments(["--url", "https://example.com"])
        self.assertEqual(parser.url, "https://example.com")
        self.assertEqual(parser.format, "markdown") # Default
        self.assertFalse(parser.headless)
        
        # Test complex args
        args = ["--input", "file.txt", "--format", "pdf", "--headless", "--workers", "max"]
        parser = cli.parse_arguments(args)
        self.assertEqual(parser.input, "file.txt")
        self.assertEqual(parser.format, "pdf")
        self.assertTrue(parser.headless)
        self.assertEqual(parser.workers, "max")

    @patch('web_scraper_toolkit.cli.WebCrawler')
    def test_main_execution_single_url(self, MockCrawler):
        # Mocking the Crawler
        instance = MockCrawler.return_value
        instance.run = AsyncMock(return_value="Success")
        
        # Mock sys.argv
        test_args = ["web-scraper", "--url", "http://example.com", "--format", "json"]
        with patch.object(sys, 'argv', test_args):
            cli.main()
            
        # Verify Config was created
        MockCrawler.assert_called_once()
        # Verify run was called
        instance.run.assert_called_once()
        _, kwargs = instance.run.call_args
        self.assertEqual(kwargs['urls'], ["http://example.com"])
        self.assertEqual(kwargs['output_format'], "json")

    @patch('web_scraper_toolkit.cli.load_urls_from_source')
    @patch('web_scraper_toolkit.cli.WebCrawler')
    def test_main_execution_input_file(self, MockCrawler, mock_load):
        # Mock file loader
        mock_load.return_value = ["https://site-a.example.com", "https://site-b.example.com"]
        
        instance = MockCrawler.return_value
        instance.run = AsyncMock(return_value="Success")
        
        test_args = ["web-scraper", "--input", "list.txt"]
        with patch.object(sys, 'argv', test_args):
            cli.main()
            
        # Verify loader called
        mock_load.assert_called_with("list.txt")
        # Verify run called with list
        _, kwargs = instance.run.call_args
        self.assertEqual(kwargs['urls'], ["https://site-a.example.com", "https://site-b.example.com"])

    @patch('web_scraper_toolkit.extract_sitemap_tree', new_callable=AsyncMock)
    def test_site_tree_mode(self, mock_tree):
        mock_tree.return_value = ["https://example.com/item1"]
        
        # Redirect output to tests_output for cleanliness
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../tests_output'))
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "sitemap_tree.csv")
        
        # Override argv to include output_name
        test_args = ["web-scraper", "--input", "https://example.com/sitemap.xml", "--site-tree", "--output-name", output_file]
        
        # We also need to mock print or file writing, as main() prints result or writes file
        # But we just want to ensure it calls extract_sitemap_tree
        with patch.object(sys, 'argv', test_args):
            # main() might exit? No, it just finishes.
            cli.main()
            
        mock_tree.assert_called_with("https://example.com/sitemap.xml")

if __name__ == '__main__':
    unittest.main()
