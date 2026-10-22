#!/usr/bin/env python3
"""
AI Crawler Checker & llms.txt Generator
=======================================

Audit how a website's robots.txt treats AI crawlers (GPTBot, ClaudeBot,
PerplexityBot, Google-Extended, ...), check whether the site publishes an
llms.txt file, and generate a starter llms.txt from the site's sitemap.

No third-party dependencies - Python 3.9+ standard library only.

Usage:
    python ai_crawler_checker.py https://example.com
    python ai_crawler_checker.py https://example.com --paths /blog/ /pricing
    python ai_crawler_checker.py https://example.com --format markdown -o report.md
    python ai_crawler_checker.py https://example.com --generate-llms llms.txt
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser

__version__ = "1.0.0"

DEFAULT_UA = f"AICrawlerChecker/{__version__} (+https://github.com/RyanShojae/ai-crawler-checker)"
TIMEOUT = 15

# --------------------------------------------------------------------------
# Known AI crawlers / robots.txt tokens
# purpose: "training"  -> collects data to train models
#          "search"    -> indexes pages for AI search answers & citations
#          "user"      -> fetches a page live when a user asks the assistant
# --------------------------------------------------------------------------
AI_CRAWLERS = [
    # token,                 operator,       purpose,    note
    ("GPTBot",               "OpenAI",       "training", "Model training data"),
    ("OAI-SearchBot",        "OpenAI",       "search",   "ChatGPT Search results & citations"),
    ("ChatGPT-User",         "OpenAI",       "user",     "Live fetches requested by ChatGPT users"),
    ("ClaudeBot",            "Anthropic",    "training", "Model training data"),
    ("Claude-SearchBot",     "Anthropic",    "search",   "Claude search results & citations"),
    ("Claude-User",          "Anthropic",    "user",     "Live fetches requested by Claude users"),
    ("PerplexityBot",        "Perplexity",   "search",   "Perplexity answer index & citations"),
    ("Perplexity-User",      "Perplexity",   "user",     "Live fetches requested by Perplexity users"),
    ("Google-Extended",      "Google",       "training", "Gemini training/grounding token; does NOT affect Google Search or AI Overviews"),
    ("Googlebot",            "Google",       "search",   "Google Search, AI Overviews & AI Mode"),
    ("Bingbot",              "Microsoft",    "search",   "Bing Search & Microsoft Copilot answers"),
    ("Applebot-Extended",    "Apple",        "training", "Apple Intelligence training token"),
    ("Meta-ExternalAgent",   "Meta",         "training", "Meta AI model training"),
    ("Amazonbot",            "Amazon",       "search",   "Alexa / Amazon AI answers"),
    ("CCBot",                "Common Crawl", "training", "Open dataset used by many LLMs"),
    ("Bytespider",           "ByteDance",    "training", "ByteDance / Doubao model training"),
    ("DuckAssistBot",        "DuckDuckGo",   "search",   "DuckAssist AI answers"),
    ("MistralAI-User",       "Mistral",      "user",     "Live fetches requested by Le Chat users"),
]


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------
@dataclass
class FetchResult:
    url: str
    status: int | None
    text: str = ""
    error: str | None = None


def fetch(url: str, user_agent: str = DEFAULT_UA, max_bytes: int = 5_000_000) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read(max_bytes)
            if resp.headers.get("Content-Encoding") == "gzip" or url.endswith(".gz"):
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            charset = resp.headers.get_content_charset() or "utf-8"
            return FetchResult(url, resp.status, raw.decode(charset, errors="replace"))
    except urllib.error.HTTPError as e:
        return FetchResult(url, e.code, error=f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return FetchResult(url, None, error=str(getattr(e, "reason", e)))


def normalize_site(url: str) -> str:
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


# --------------------------------------------------------------------------
# robots.txt parser (RFC 9309: longest match wins, Allow wins ties,
# supports * and $ wildcards, grouped user-agent lines)
# --------------------------------------------------------------------------
@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[str, str]] = field(default_factory=list)  # (allow|disallow, pattern)


class RobotsTxt:
    def __init__(self, text: str):
        self.groups: list[Group] = []
        self.sitemaps: list[str] = []
        self._parse(text)

    def _parse(self, text: str) -> None:
        current: Group | None = None
        last_was_agent = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = Group()
                    self.groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if current is not None:
                    current.rules.append((key, value))
            elif key == "sitemap":
                self.sitemaps.append(value)
            else:
                last_was_agent = False

    def group_for(self, agent: str) -> tuple[Group | None, str]:
        """Return the rule group that applies to `agent` and how it matched."""
        agent_l = agent.lower()
        specific = [g for g in self.groups if agent_l in g.agents]
        if specific:
            merged = Group(agents=[agent_l], rules=[r for g in specific for r in g.rules])
            return merged, "specific"
        wildcard = [g for g in self.groups if "*" in g.agents]
        if wildcard:
            merged = Group(agents=["*"], rules=[r for g in wildcard for r in g.rules])
            return merged, "wildcard (*)"
        return None, "none"

    @staticmethod
    def _pattern_to_regex(pattern: str) -> re.Pattern:
        anchored = pattern.endswith("$")
        if anchored:
            pattern = pattern[:-1]
        regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern)
        return re.compile("^" + regex + ("$" if anchored else ""))

    def is_allowed(self, agent: str, path: str = "/") -> tuple[bool, str, str]:
        """Return (allowed, matched_rule, group_match)."""
        group, how = self.group_for(agent)
        if group is None:
            return True, "no matching group", how
        best: tuple[int, str, str] | None = None  # (length, kind, pattern)
        for kind, pattern in group.rules:
            if pattern == "":
                continue  # empty Disallow = allow everything
            if self._pattern_to_regex(pattern).match(path):
                length = len(pattern)
                if (best is None or length > best[0]
                        or (length == best[0] and kind == "allow" and best[1] == "disallow")):
                    best = (length, kind, pattern)
        if best is None:
            return True, "no rule matched", how
        return best[1] == "allow", f"{best[1].capitalize()}: {best[2]}", how


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------
@dataclass
class CrawlerResult:
    crawler: str
    operator: str
    purpose: str
    note: str
    group: str
    paths: dict[str, dict]  # path -> {"allowed": bool, "rule": str}

    @property
    def fully_allowed(self) -> bool:
        return all(v["allowed"] for v in self.paths.values())

    @property
    def fully_blocked(self) -> bool:
        return not any(v["allowed"] for v in self.paths.values())


@dataclass
class Report:
    site: str
    robots_url: str
    robots_status: int | None
    robots_found: bool
    sitemaps: list[str]
    llms_txt: dict
    crawlers: list[CrawlerResult]
    recommendations: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        for c, obj in zip(d["crawlers"], self.crawlers):
            c["status"] = status_label(obj)
        return d


def status_label(c: CrawlerResult) -> str:
    if c.fully_allowed:
        return "ALLOWED"
    if c.fully_blocked:
        return "BLOCKED"
    return "PARTIAL"


def check_llms_txt(site: str) -> dict:
    out = {}
    for name in ("llms.txt", "llms-full.txt"):
        r = fetch(f"{site}/{name}")
        found = r.status == 200 and bool(r.text.strip()) and "<html" not in r.text[:500].lower()
        out[name] = {"found": found, "status": r.status}
        if found and name == "llms.txt":
            out[name]["has_h1_title"] = bool(re.search(r"^# \S", r.text, re.M))
            out[name]["link_count"] = len(re.findall(r"\[[^\]]+\]\([^)]+\)", r.text))
    return out


def build_recommendations(rep: Report) -> list[str]:
    recs: list[str] = []
    by_name = {c.crawler: c for c in rep.crawlers}
    if not rep.robots_found:
        recs.append("No robots.txt found. Add one so you can explicitly control AI crawler access.")
    search_blocked = [c.crawler for c in rep.crawlers if c.purpose == "search" and not c.fully_allowed]
    if search_blocked:
        recs.append(
            "AI *search* crawlers are restricted (" + ", ".join(search_blocked) + "). "
            "This can remove the site from AI answers and citations (GEO visibility). "
            "Unblock them unless this is intentional.")
    if by_name.get("Googlebot") and not by_name["Googlebot"].fully_allowed:
        recs.append("Googlebot is restricted - this affects classic Google rankings AND AI Overviews / AI Mode.")
    if by_name.get("Bingbot") and not by_name["Bingbot"].fully_allowed:
        recs.append("Bingbot is restricted - this affects Bing and Microsoft Copilot answers.")
    training_open = [c.crawler for c in rep.crawlers if c.purpose == "training" and c.fully_allowed]
    if training_open:
        recs.append(
            "Training crawlers are allowed (" + ", ".join(training_open) + "). Fine for brand reach; "
            "block them individually if you don't want content used for model training. "
            "Blocking training bots does not remove you from AI search answers.")
    if by_name.get("Google-Extended") and by_name["Google-Extended"].fully_blocked:
        recs.append("Google-Extended is blocked. Note: this does not remove the site from Google AI Overviews.")
    wildcard_only = [c.crawler for c in rep.crawlers if c.group == "wildcard (*)"]
    if len(wildcard_only) == len(rep.crawlers) and rep.robots_found:
        recs.append("No AI crawler has its own rules; all fall back to 'User-agent: *'. "
                    "Add explicit groups to make your AI policy intentional and auditable.")
    if not rep.sitemaps:
        recs.append("No Sitemap: line in robots.txt. Add one to help search and AI crawlers discover content.")
    if not rep.llms_txt.get("llms.txt", {}).get("found"):
        recs.append("No /llms.txt found. Generate one with --generate-llms to give LLMs a curated map of key pages.")
    elif not rep.llms_txt["llms.txt"].get("has_h1_title"):
        recs.append("llms.txt exists but has no '# Title' line required by the llms.txt proposal.")
    return recs


def audit(site: str, paths: list[str]) -> Report:
    site = normalize_site(site)
    robots_url = f"{site}/robots.txt"
    r = fetch(robots_url)
    found = r.status == 200
    # RFC 9309: 4xx = no restrictions; 5xx/unreachable = assume full disallow
    if found:
        robots = RobotsTxt(r.text)
    elif r.status is not None and 400 <= r.status < 500:
        robots = RobotsTxt("")
    else:
        robots = RobotsTxt("User-agent: *\nDisallow: /")

    crawlers = []
    for token, operator, purpose, note in AI_CRAWLERS:
        results, how = {}, "none"
        for p in paths:
            allowed, rule, how = robots.is_allowed(token, p)
            results[p] = {"allowed": allowed, "rule": rule}
        crawlers.append(CrawlerResult(token, operator, purpose, note, how, results))

    rep = Report(site, robots_url, r.status, found, robots.sitemaps, check_llms_txt(site), crawlers, [])
    rep.recommendations = build_recommendations(rep)
    return rep


# --------------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------------
def render_text(rep: Report) -> str:
    lines = [f"AI Crawler Audit: {rep.site}",
             "=" * (18 + len(rep.site)),
             f"robots.txt : {'found' if rep.robots_found else 'NOT found'} (HTTP {rep.robots_status})",
             f"llms.txt   : {'found' if rep.llms_txt['llms.txt']['found'] else 'NOT found'}",
             f"Sitemaps   : {', '.join(rep.sitemaps) or 'none declared'}", ""]
    w = max(len(c.crawler) for c in rep.crawlers)
    lines.append(f"{'Crawler'.ljust(w)}  {'Operator'.ljust(12)}  {'Purpose'.ljust(8)}  Status    Rule")
    lines.append("-" * (w + 60))
    for c in rep.crawlers:
        rule = next(iter(c.paths.values()))["rule"] if len(c.paths) == 1 else \
            "; ".join(f"{p} -> {'ok' if v['allowed'] else 'blocked'}" for p, v in c.paths.items())
        lines.append(f"{c.crawler.ljust(w)}  {c.operator.ljust(12)}  {c.purpose.ljust(8)}  "
                     f"{status_label(c).ljust(8)}  {rule}")
    lines += ["", "Recommendations:"] + [f"  {i}. {r}" for i, r in enumerate(rep.recommendations, 1)]
    return "\n".join(lines)


def render_markdown(rep: Report) -> str:
    icon = {"ALLOWED": "✅ Allowed", "BLOCKED": "⛔ Blocked", "PARTIAL": "⚠️ Partial"}
    md = [f"# AI Crawler Audit: {rep.site}", "",
          "| Check | Result |", "|---|---|",
          f"| robots.txt | {'Found' if rep.robots_found else 'Not found'} (HTTP {rep.robots_status}) |",
          f"| llms.txt | {'Found' if rep.llms_txt['llms.txt']['found'] else 'Not found'} |",
          f"| Sitemaps | {', '.join(rep.sitemaps) or 'None declared'} |", "",
          "## Crawler access", "",
          "| Crawler | Operator | Purpose | Status | Matched rule |", "|---|---|---|---|---|"]
    for c in rep.crawlers:
        rule = "<br>".join(f"`{p}` {v['rule']}" for p, v in c.paths.items())
        md.append(f"| {c.crawler} | {c.operator} | {c.purpose} | {icon[status_label(c)]} | {rule} |")
    md += ["", "## Recommendations", ""] + [f"{i}. {r}" for i, r in enumerate(rep.recommendations, 1)]
    return "\n".join(md) + "\n"


# --------------------------------------------------------------------------
# llms.txt generator
# --------------------------------------------------------------------------
class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.description, self._in_title = "", "", False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and not self.description:
            if a.get("name", "").lower() == "description" or a.get("property", "").lower() == "og:description":
                self.description = a.get("content", "").strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def page_meta(url: str) -> tuple[str, str]:
    r = fetch(url, max_bytes=500_000)
    if r.status != 200:
        return "", ""
    p = _MetaParser()
    try:
        p.feed(r.text)
    except Exception:
        pass
    return re.sub(r"\s+", " ", p.title).strip(), re.sub(r"\s+", " ", p.description).strip()


def sitemap_urls(sitemap_url: str, limit: int, _depth: int = 0) -> list[str]:
    r = fetch(sitemap_url)
    if r.status != 200 or _depth > 2:
        return []
    try:
        root = ET.fromstring(r.text.encode("utf-8"))
    except ET.ParseError:
        return []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []
    if root.tag.endswith("sitemapindex"):
        for loc in root.findall("sm:sitemap/sm:loc", ns):
            urls += sitemap_urls(loc.text.strip(), limit - len(urls), _depth + 1)
            if len(urls) >= limit:
                break
    else:
        urls = [loc.text.strip() for loc in root.findall("sm:url/sm:loc", ns) if loc.text]
    return urls[:limit]


def section_for(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/")
    if not path:
        return "Main"
    first = path.split("/")[0]
    return first.replace("-", " ").replace("_", " ").title()


def generate_llms_txt(site: str, limit: int = 50) -> str:
    site = normalize_site(site)
    r = fetch(f"{site}/robots.txt")
    sitemaps = RobotsTxt(r.text).sitemaps if r.status == 200 else []
    if not sitemaps:
        sitemaps = [f"{site}/sitemap.xml"]
    urls: list[str] = []
    for sm in sitemaps:
        urls += [u for u in sitemap_urls(sm, limit - len(urls)) if u not in urls]
        if len(urls) >= limit:
            break

    home_title, home_desc = page_meta(site + "/")
    site_name = re.split(r"\s[|\-–—]\s", home_title)[0].strip() if home_title else urllib.parse.urlparse(site).netloc

    sections: dict[str, list[str]] = {}
    for u in urls:
        title, desc = page_meta(u)
        title = title or urllib.parse.urlparse(u).path.strip("/").split("/")[-1].replace("-", " ").title() or site_name
        entry = f"- [{title}]({u})" + (f": {desc}" if desc else "")
        sections.setdefault(section_for(u), []).append(entry)

    out = [f"# {site_name}", ""]
    if home_desc:
        out += [f"> {home_desc}", ""]
    out += [f"This file helps large language models understand the most important content on {site}.", ""]
    if not sections:
        out += ["## Main", "", f"- [Home]({site}/)", ""]
    for name, entries in sections.items():
        if name == "Main":
            continue
        out += [f"## {name}", ""] + entries + [""]
    if "Main" in sections:
        out += ["## Optional", ""] + sections["Main"] + [""]
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit AI crawler access and generate llms.txt for a website.")
    ap.add_argument("site", help="Website URL, e.g. https://example.com")
    ap.add_argument("--paths", nargs="+", default=["/"], help="Paths to test (default: /)")
    ap.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    ap.add_argument("-o", "--output", help="Write the report to a file")
    ap.add_argument("--generate-llms", metavar="FILE", help="Generate an llms.txt from the sitemap and save it")
    ap.add_argument("--limit", type=int, default=50, help="Max sitemap URLs for llms.txt (default 50)")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    if args.generate_llms:
        content = generate_llms_txt(args.site, args.limit)
        with open(args.generate_llms, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"llms.txt written to {args.generate_llms}")
        return 0

    rep = audit(args.site, args.paths)
    if args.format == "json":
        out = json.dumps(rep.to_dict(), indent=2)
    elif args.format == "markdown":
        out = render_markdown(rep)
    else:
        out = render_text(rep)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Report written to {args.output}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
