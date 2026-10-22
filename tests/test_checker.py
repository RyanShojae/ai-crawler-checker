import os
import sys
import threading
import unittest
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_crawler_checker as acc  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "site")


class RobotsParserTests(unittest.TestCase):
    def test_specific_group_overrides_wildcard(self):
        r = acc.RobotsTxt("User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n")
        self.assertFalse(r.is_allowed("GPTBot", "/")[0])
        self.assertTrue(r.is_allowed("ClaudeBot", "/")[0])

    def test_agent_matching_is_case_insensitive(self):
        r = acc.RobotsTxt("User-agent: gptbot\nDisallow: /\n")
        self.assertFalse(r.is_allowed("GPTBot", "/page")[0])

    def test_longest_match_wins(self):
        r = acc.RobotsTxt("User-agent: *\nDisallow: /blog/\nAllow: /blog/public/\n")
        self.assertFalse(r.is_allowed("PerplexityBot", "/blog/private")[0])
        self.assertTrue(r.is_allowed("PerplexityBot", "/blog/public/post")[0])

    def test_allow_wins_tie(self):
        r = acc.RobotsTxt("User-agent: *\nDisallow: /page\nAllow: /page\n")
        self.assertTrue(r.is_allowed("ClaudeBot", "/page")[0])

    def test_wildcards_and_end_anchor(self):
        r = acc.RobotsTxt("User-agent: *\nDisallow: /*.pdf$\nDisallow: /*?session=\n")
        self.assertFalse(r.is_allowed("GPTBot", "/files/report.pdf")[0])
        self.assertTrue(r.is_allowed("GPTBot", "/files/report.pdf.html")[0])
        self.assertFalse(r.is_allowed("GPTBot", "/shop?session=123")[0])

    def test_empty_disallow_allows_everything(self):
        r = acc.RobotsTxt("User-agent: *\nDisallow:\n")
        self.assertTrue(r.is_allowed("CCBot", "/anything")[0])

    def test_grouped_user_agents(self):
        r = acc.RobotsTxt("User-agent: GPTBot\nUser-agent: CCBot\nDisallow: /\n")
        self.assertFalse(r.is_allowed("GPTBot", "/")[0])
        self.assertFalse(r.is_allowed("CCBot", "/")[0])
        self.assertTrue(r.is_allowed("ClaudeBot", "/")[0])

    def test_comments_and_sitemaps(self):
        r = acc.RobotsTxt("# hello\nUser-agent: * # all\nDisallow: /tmp # temp\nSitemap: https://x.com/sitemap.xml\n")
        self.assertFalse(r.is_allowed("GPTBot", "/tmp/a")[0])
        self.assertEqual(r.sitemaps, ["https://x.com/sitemap.xml"])

    def test_no_robots_means_allowed(self):
        self.assertTrue(acc.RobotsTxt("").is_allowed("GPTBot", "/")[0])


class LiveSiteTests(unittest.TestCase):
    """Spin up a local web server with a fixture site and run the full audit."""

    @classmethod
    def setUpClass(cls):
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        handler = partial(QuietHandler, directory=FIXTURE_DIR)
        cls.server = HTTPServer(("127.0.0.1", 0), handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        # Render templates so URLs point at the random port
        for src, dst in (("sitemap.template.xml", "sitemap.xml"), ("robots.template.txt", "robots.txt")):
            with open(os.path.join(FIXTURE_DIR, src), encoding="utf-8") as f:
                text = f.read().replace("{BASE}", cls.base).replace("{SITEMAP}", cls.base + "/sitemap.xml")
            with open(os.path.join(FIXTURE_DIR, dst), "w", encoding="utf-8") as f:
                f.write(text)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        for name in ("sitemap.xml", "robots.txt"):
            os.remove(os.path.join(FIXTURE_DIR, name))

    def test_audit(self):
        rep = acc.audit(self.base, ["/", "/blog/"])
        status = {c.crawler: acc.status_label(c) for c in rep.crawlers}
        self.assertTrue(rep.robots_found)
        self.assertEqual(status["GPTBot"], "BLOCKED")
        self.assertEqual(status["OAI-SearchBot"], "ALLOWED")
        self.assertEqual(status["CCBot"], "BLOCKED")
        self.assertEqual(status["PerplexityBot"], "PARTIAL")
        self.assertFalse(rep.llms_txt["llms.txt"]["found"])
        self.assertTrue(any("llms.txt" in r for r in rep.recommendations))
        self.assertTrue(any("PerplexityBot" in r for r in rep.recommendations))

    def test_renderers(self):
        rep = acc.audit(self.base, ["/"])
        self.assertIn("GPTBot", acc.render_text(rep))
        self.assertIn("| GPTBot |", acc.render_markdown(rep))
        self.assertIn("crawlers", rep.to_dict())

    def test_generate_llms_txt(self):
        out = acc.generate_llms_txt(self.base)
        self.assertTrue(out.startswith("# Glow Studio"))
        self.assertIn("> Clean beauty and skincare tips", out)
        self.assertIn("## Blog", out)
        self.assertIn("[Morning Skincare Routine]", out)


if __name__ == "__main__":
    unittest.main()
