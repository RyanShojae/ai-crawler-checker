# AI Crawler Checker & llms.txt Generator

![Tests](https://github.com/RyanShojae/ai-crawler-checker/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A **Generative Engine Optimization (GEO)** tool that shows whether AI search engines and LLMs can reach a website, and builds an `llms.txt` file to help them understand it.

If a site's `robots.txt` blocks the wrong bot, it can disappear from **ChatGPT Search, Perplexity, Claude, Gemini, Microsoft Copilot and Google AI Overviews** without anyone noticing. This tool finds those problems in seconds.

## Features

- **Audits 18 AI crawlers** from OpenAI, Anthropic, Perplexity, Google, Microsoft, Apple, Meta, Amazon, Common Crawl and others.
- **Labels each crawler by purpose:**
  - `training`: collects data to train models
  - `search`: indexes pages for AI answers and citations, which matters most for GEO
  - `user`: fetches a page live when someone asks an assistant
- **Reads `robots.txt` the way crawlers do (RFC 9309):** user-agent groups, longest-match rules, `Allow` winning ties, and `*` / `$` wildcards. Python's built-in `robotparser` gets these wrong.
- **Tests specific paths,** such as `/blog/` or `/products/`, not only the homepage.
- **Checks for `llms.txt` and `llms-full.txt`** and validates the basic format.
- **Gives GEO-focused recommendations.** For example, it explains that blocking `Google-Extended` does not remove a site from AI Overviews, and that blocking training bots is different from blocking AI search bots.
- **Generates a starter `llms.txt`** from the site's XML sitemap, using each page's title and meta description, grouped by section.
- Outputs **text, Markdown or JSON**, so reports can go to clients or into dashboards.
- **No dependencies:** pure Python standard library.

## Quick start

```bash
git clone https://github.com/RyanShojae/ai-crawler-checker.git
cd ai-crawler-checker

# Audit a site
python ai_crawler_checker.py https://example.com

# Test specific sections of the site
python ai_crawler_checker.py https://example.com --paths / /blog/ /products/

# Client-ready Markdown report
python ai_crawler_checker.py https://example.com --format markdown -o report.md

# JSON for dashboards / automation
python ai_crawler_checker.py https://example.com --format json

# Generate an llms.txt from the sitemap (first 50 URLs)
python ai_crawler_checker.py https://example.com --generate-llms llms.txt --limit 50
```

## Example output

The output below comes from the test fixture site in `tests/fixtures/site`, a fictional beauty salon with a mixed AI-bot policy:

```text
Crawler             Operator      Purpose   Status    Rule
------------------------------------------------------------------------------
GPTBot              OpenAI        training  BLOCKED   / -> blocked; /blog/ -> blocked
OAI-SearchBot       OpenAI        search    ALLOWED   / -> ok; /blog/ -> ok
ClaudeBot           Anthropic     training  ALLOWED   / -> ok; /blog/ -> ok
PerplexityBot       Perplexity    search    PARTIAL   / -> ok; /blog/ -> blocked
Googlebot           Google        search    ALLOWED   / -> ok; /blog/ -> ok
CCBot               Common Crawl  training  BLOCKED   / -> blocked; /blog/ -> blocked
...

Recommendations:
  1. AI *search* crawlers are restricted (PerplexityBot). This can remove the site
     from AI answers and citations (GEO visibility). Unblock them unless intentional.
  2. Training crawlers are allowed (ClaudeBot, Google-Extended, ...). Blocking
     training bots does not remove you from AI search answers.
  3. No /llms.txt found. Generate one with --generate-llms.
```

Full examples:

- [Text report](examples/sample-report.txt)
- [Markdown report](examples/sample-report.md)
- [Generated llms.txt](examples/sample-llms.txt)

## Why this matters for GEO

| Situation | Impact |
|---|---|
| `OAI-SearchBot` blocked | Site can't be cited in **ChatGPT Search** answers |
| `PerplexityBot` blocked | Site drops out of **Perplexity** citations |
| `Bingbot` blocked | Hurts **Bing** and **Microsoft Copilot** visibility |
| `Googlebot` blocked | Hurts Google rankings **and** AI Overviews / AI Mode |
| `GPTBot` / `ClaudeBot` / `CCBot` blocked | Content isn't used for model training. Search visibility is **not** directly affected |
| `Google-Extended` blocked | Opts out of Gemini training. Does **not** affect AI Overviews |
| No `llms.txt` | LLMs have no curated summary of the site's most important pages |

A common mistake is adding `User-agent: GPTBot / Disallow: /` and believing the site is now "protected from AI." It is, but only from training. Search bots like `OAI-SearchBot` decide whether the brand gets cited.

## Run the tests

```bash
python -m unittest discover -s tests -v
```

The tests cover the RFC 9309 matching rules and run a full audit and `llms.txt` generation against a local fixture website. GitHub Actions runs them on Python 3.9–3.13.

## Roadmap

- [ ] Check meta robots / `X-Robots-Tag` (`noai`, `noimageai`, `nosnippet`)
- [ ] Bulk audit from a CSV list of domains
- [ ] Verify crawler IPs against published IP ranges
- [ ] Simple web UI

## Author

**Ryan Shojae**, SEO & Generative Engine Optimization (GEO) Strategist.
Contact: ryansho@yahoo.com

## License

MIT
