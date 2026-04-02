# Master CRM — Backend Claude Code Instructions

## IDENTITY
Running the Master CRM pipeline for Ewing Gillaspy's three businesses:
- **Next Chapter** (`next_chapter`) — Boutique M&A advisory for home services
- **AND Capital** (`and_capital`) — PE fund management, LP fundraising
- **RevsUp** (`revsup`) — Contingent recruiting for revenue roles at SaaS companies

Plus standalone: `the_forge`, `biolev`, `sea_sweet`, `precision_exploration`

## NORTH STAR DOCUMENTS
Entity Classification Guide (`data/north-star/NORTH-STAR-entity-classification-guide.md`) and Infrastructure Map (`data/north-star/NORTH-STAR-infrastructure-map.md`) are the authority. Read them before entity or campaign decisions.

## ENTITY RULES
- Every transactional row MUST carry an `entity` field
- `do_not_call` is UNIVERSAL — no entity column. One DNC = blocked everywhere.
- Campaign names carry entity prefix: `AND-`, `NC-`, `RU-`
- Use `lib/classification.py` for deterministic entity classification

## LLM CONFIGURATION
- **Claude Code CLI (`claude -p`):** $0.00 via subscription. Primary.
- **DeepSeek V3:** OpenRouter $0.004/call — auditor + validator agents
- **Gemini 2.5 Flash Lite:** OpenRouter $0.001/call — researcher agent
- **GPT-4o Mini:** OpenRouter $0.002/call — executor agent

## BUYER HUB MAINTENANCE

After adding buyers to `engagement_buyers` or generating 1-pager HTML:
```bash
python3 scripts/refresh_hub_buyers.py --proposal <id> --hub public/<slug>-hub.html --prefix <slug>
```
Never deploy a hub page without running this first.

## BUYER SCORING

See root CLAUDE.md for scoring table (8/6/4). Adjacent vertical definitions:
- **Floor care/cleaning:** cleaning, restoration, janitorial, facility services, pest, home services
- **HVAC/mechanical:** HVAC, plumbing, electrical, home services, building services
- **Water treatment:** water treatment, purification, softening, infrastructure, utilities
- **HR tech/B2B media:** HCM, payroll, talent management, recruiting, L&D, B2B HR media
- **Precast concrete:** precast, concrete manufacturing, infrastructure materials, pipe, building products
- **PE firms:** HIGH only with confirmed portfolio company OR deal in seller's vertical

## CAMPAIGNS (17)

| Campaign | Entity | Channel | Purpose |
|----------|--------|---------|---------|
| NC-SELL-LETTER | next_chapter | Direct mail | Ask if considering selling |
| NC-SELL-CALL | next_chapter | Cold call | Qualify interest in selling |
| NC-BUY-OUTREACH | next_chapter | Cold call/email | Match buyers to businesses |
| NC-TRANSCRIPT | next_chapter | Internal | Extract leads from calls |
| NC-TAM | next_chapter | Scraping | Build total addressable market |
| AND-LP-LETTER | and_capital | Direct mail | Introduce funds, request meeting |
| AND-LP-CALL | and_capital | Cold call | Book fund presentations |
| AND-LP-LINKEDIN | and_capital | LinkedIn | Warm LP introductions |
| AND-DEAL-SOURCE | and_capital | Cold call | Source deal flow from bankers |
| AND-FUND-DISTRO | and_capital | Email | Share fund decks |
| RU-CLIENT | revsup | Email/LinkedIn | Win recruiting engagements |
| RU-CANDIDATE | revsup | LinkedIn/boards | Find candidates |
| RU-REFERRAL | revsup | Referral | Inbound from network |
| FORGE-BOOMERANG | the_forge | Email | Athlete recruitment |
| BIOLEV-SALE | biolev | Meeting | BioLev sale (static assets) |
| SEASWEET-ROOFING | sea_sweet | Cold call | Roofing rollup |
| PEC-FRAUD | precision_exploration | Manual | NEVER automate |
