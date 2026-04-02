# Debbie Buyer Review System

**Built:** 2026-04-01
**Purpose:** Research and review potential acquirers for HR.com Ltd deal
**Reviewer:** Debbie McGrath (HR.com CEO)

## Architecture

```
scripts/run_one_buyer_test.py    ← CLI: runs research for one buyer
  ├── Exa API searches (13+ per buyer, ~$0.15 each)
  ├── Claude synthesis (HTML narratives per section)
  ├── Product discovery → per-product review extraction
  ├── Golden nuggets extraction (structured array)
  ├── Stock data fetch (Exa + Claude)
  └── Writes:
      ├── public/data/debbie-research-{slug}.json   (per-buyer)
      ├── public/data/debbie-buyers-manifest.json    (index)
      ├── public/data/debbie-buyer-research.json     (combined, legacy)
      └── git commit + push → Vercel auto-deploys

public/debbie-review-index.html  ← Dashboard: card grid of all buyers
public/debbie-buyer-review.html  ← Template: ?buyer={slug} loads one buyer
```

## CLI Usage

```bash
# Full run with stock data and logo
python3 scripts/run_one_buyer_test.py \
  --buyer "ADP" --city Roseland --state NJ \
  --ticker ADP --domain adp.com

# Dry run (no deploy)
python3 scripts/run_one_buyer_test.py \
  --buyer "Deel" --city "San Francisco" --state CA \
  --ticker "" --domain deel.com --skip-deploy

# Available flags
--buyer    REQUIRED  Company name
--city     REQUIRED  HQ city
--state    REQUIRED  HQ state
--ticker   optional  Stock ticker (PAYX, SAP, WDAY)
--domain   optional  Company domain for Clearbit logo
--type     optional  Buyer type (default: Strategic)
--score    optional  Fit score (default: 8)
--skip-deploy        Skip git commit+push
```

## Known Buyer Tickers

| Buyer | Ticker | Exchange | Domain |
|-------|--------|----------|--------|
| Paychex | PAYX | NASDAQ | paychex.com |
| SAP SuccessFactors | SAP | NYSE | sap.com |
| Workday | WDAY | NASDAQ | workday.com |
| ADP | ADP | NASDAQ | adp.com |
| Thoma Bravo | — | Private | thomabravo.com |
| Microsoft | MSFT | NASDAQ | microsoft.com |
| Salesforce | CRM | NYSE | salesforce.com |
| IBM | IBM | NYSE | ibm.com |
| Oracle HCM | ORCL | NYSE | oracle.com |
| UKG | — | Private | ukg.com |
| Rippling | — | Private | rippling.com |
| BambooHR | — | Private | bamboohr.com |

## Data Contract (per-buyer JSON)

```json
{
  "buyer_name": "Paychex",
  "buyer_slug": "paychex",
  "buyer_type": "Strategic",
  "buyer_city": "Rochester",
  "buyer_state": "NY",
  "fit_score": 8,
  "logo_domain": "paychex.com",
  "ticker": "PAYX",
  "stock_price": "$140.22",
  "price_change_24mo": 16.8,
  "market_cap": "$33.5B",
  "sections": {
    "ceo_vision": "<p>HTML narrative</p>",
    "ma_appetite": "<p>...</p>",
    "competitive_moat": "<p>...</p>",
    "earnings_quotes": "<p>...</p>",
    "approach_strategy": "<p>...</p>"
  },
  "hr_media_business": {"narrative": "<p>HTML</p>"},
  "hr_domain_name": {"narrative": "<p>HTML</p>"},
  "market_reputation": {
    "narrative": "<p>HTML summary</p>",
    "products_discovered": ["Product A", "Product B"],
    "summary_stats": {"total_reviews_scraped": 45, "reviews_passing_threshold": 19},
    "product_reviews": {
      "Product A": {
        "positive": [{"text": "...", "category": "usability", "source": "G2", "source_url": "", "scores": {"informativeness": 2, "specificity": 2, "polarity": 3}}],
        "negative": [{"text": "...", "category": "support", ...}],
        "total_raw": 15
      }
    }
  },
  "strategic_fit": "<p>Direct HTML string</p>",
  "golden_nuggets": [
    {"quote": "exact quote", "speaker": "Name, Title", "opener": "conversation starter", "why": "M&A relevance"}
  ],
  "source_urls": {"section_key": ["url1", "url2"]}
}
```

## Critical Rules

1. **golden_nuggets** MUST be an array of objects, never an HTML string
2. **market_reputation** requires product discovery BEFORE review extraction — without this, all reviews collapse into one generic bucket
3. **stock_price** must include `$` prefix; **price_change_24mo** is the field name (not _pct)
4. **Logos** from Clearbit: `https://logo.clearbit.com/{domain}` — free, no key
5. **Each buyer gets its own page** — never render multiple buyers on one page
6. **Exa costDollars** returns `{"total": float}` dict, not a raw float

## Research Sections (10)

| Section | Key | Data Location | Notes |
|---------|-----|---------------|-------|
| HR.com Media Business | hr_media_business | `.hr_media_business.narrative` | Object with narrative key |
| HR.com Domain Name | hr_domain_name | `.hr_domain_name.narrative` | Object with narrative key |
| Market Reputation | market_reputation | `.market_reputation` | Structured: products_discovered + product_reviews |
| Pain/Gain Match | pain_gain_match | computed from market_reputation | Auto-generated from negative reviews by category |
| Strategic Fit | strategic_fit | `.strategic_fit` | Direct HTML string |
| CEO Vision | ceo_vision | `.sections.ceo_vision` | In sections sub-object |
| M&A Appetite | ma_appetite | `.sections.ma_appetite` | In sections sub-object |
| Competitive Moat | competitive_moat | `.sections.competitive_moat` | In sections sub-object |
| Earnings Quotes | earnings_quotes | `.sections.earnings_quotes` | In sections sub-object |
| Approach Strategy | approach_strategy | `.sections.approach_strategy` | In sections sub-object |

## Cost per Buyer

~$0.15-0.25 Exa + ~$0.02 Claude synthesis = ~$0.20 total per buyer
68 buyers × $0.20 = ~$14 total for full HR.com buyer research
