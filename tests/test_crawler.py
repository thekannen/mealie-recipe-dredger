from mealie_recipe_dredger.crawler import SitemapCrawler


class DummyResponse:
    def __init__(self, status_code=200, content=b"", text="", url=""):
        self.status_code = status_code
        self.content = content
        self.text = text
        self.url = url

    def close(self):
        return None


class DummySession:
    def __init__(self, xml_content: bytes):
        self.xml_content = xml_content

    def get(self, url: str, timeout: int = 10, **kwargs):
        return DummyResponse(status_code=200, content=self.xml_content, text=self.xml_content.decode("utf-8"))

    def head(self, url: str, timeout: int = 5, allow_redirects: bool = True, **kwargs):
        return DummyResponse(status_code=404, url="")


class DummyStorage:
    def get_cached_sitemap(self, _site_url):
        return None

    def cache_sitemap(self, _site_url, _sitemap_url, _urls):
        return None


def test_fetch_sitemap_urls_ignores_image_loc_entries():
    xml = b"""<?xml version='1.0' encoding='UTF-8'?>
<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9' xmlns:image='http://www.google.com/schemas/sitemap-image/1.1'>
  <url>
    <loc>https://example.com/recipe-1/</loc>
    <image:image>
      <image:loc>https://example.com/wp-content/uploads/image1.jpg</image:loc>
    </image:image>
  </url>
</urlset>
"""
    crawler = SitemapCrawler(DummySession(xml), DummyStorage())
    urls = crawler.fetch_sitemap_urls("https://example.com/sitemap.xml")
    assert urls == ["https://example.com/recipe-1/"]
