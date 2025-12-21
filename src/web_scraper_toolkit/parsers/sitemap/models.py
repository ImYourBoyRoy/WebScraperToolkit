# ./src/web_scraper_toolkit/parsers/sitemap/models.py
"""
Sitemap Models & Constants
==========================
"""

# Common sitemap paths to probe
COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap-index.xml.gz",
    "/sitemap.xml.gz",
    "/sitemap-index.html",
    "/sitemap.html",
    "/sitemap.txt",
    "/sitemap_index.txt",
    "/wp-sitemap.xml",
    "/wp-sitemap-index.xml",
    "/news-sitemap.xml",
    "/post-sitemap.xml",
    "/page-sitemap.xml",
    # WordPress specific
    "/wp-sitemap-posts-post-1.xml",
    "/wp-sitemap-posts-page-1.xml",
]
