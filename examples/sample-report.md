# AI Crawler Audit: https://glowstudio.example

| Check | Result |
|---|---|
| robots.txt | Found (HTTP 200) |
| llms.txt | Not found |
| Sitemaps | https://glowstudio.example/sitemap.xml |

## Crawler access

| Crawler | Operator | Purpose | Status | Matched rule |
|---|---|---|---|---|
| GPTBot | OpenAI | training | ⛔ Blocked | `/` Disallow: /<br>`/blog/` Disallow: / |
| OAI-SearchBot | OpenAI | search | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| ChatGPT-User | OpenAI | user | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| ClaudeBot | Anthropic | training | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| Claude-SearchBot | Anthropic | search | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| Claude-User | Anthropic | user | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| PerplexityBot | Perplexity | search | ⚠️ Partial | `/` no rule matched<br>`/blog/` Disallow: /blog/ |
| Perplexity-User | Perplexity | user | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| Google-Extended | Google | training | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| Googlebot | Google | search | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| Bingbot | Microsoft | search | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| Applebot-Extended | Apple | training | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| Meta-ExternalAgent | Meta | training | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| Amazonbot | Amazon | search | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| CCBot | Common Crawl | training | ⛔ Blocked | `/` Disallow: /<br>`/blog/` Disallow: / |
| Bytespider | ByteDance | training | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| DuckAssistBot | DuckDuckGo | search | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |
| MistralAI-User | Mistral | user | ✅ Allowed | `/` no rule matched<br>`/blog/` no rule matched |

## Recommendations

1. AI *search* crawlers are restricted (PerplexityBot). This can remove the site from AI answers and citations (GEO visibility). Unblock them unless this is intentional.
2. Training crawlers are allowed (ClaudeBot, Google-Extended, Applebot-Extended, Meta-ExternalAgent, Bytespider). Fine for brand reach; block them individually if you don't want content used for model training. Blocking training bots does not remove you from AI search answers.
3. No /llms.txt found. Generate one with --generate-llms to give LLMs a curated map of key pages.
