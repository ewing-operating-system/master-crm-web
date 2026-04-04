# Prompt: Debbie Buyer Research — 16 Companies

**Created:** April 3, 2026
**Deal:** Next Chapter → hr.com (Debbie McGrath)
**Vertical:** `hr_media` | **Entity:** `next_chapter`

---

Run the full Debbie buyer research process for the following 16 companies and create buyer pages for each in master-crm-web.

The companies are: Workday, Oracle, Accenture, IBM, ADP, Paychex, TriNet, UKG, Paylocity, Rippling, Gusto, Deel, Hibob, Ceridian, BambooHR, and Cornerstone OnDemand.

Vertical is `hr_media`, entity is `next_chapter` (from config). This is for the Next Chapter hr.com deal (Debbie McGrath). These are potential acquirers of HR.com's three assets: the hr.com domain, the HR.com media business, and the My People platform.

Before starting, read the process docs:

- `docs/DEBBIE-REVIEW-SYSTEM.md` — system architecture and CLI commands
- `lib/config/verticals/hr_media.json` — the vertical config (10 research sections, synthesis prompts, buyer scoring criteria)
- `backend/agents/agent-playbook-page-creator.md` — the page creation playbook
- `backend/data/meetings/hrcom-debbie-mcgrath-2026-03-23.json` — deal context

For each buyer, run the full pipeline using `scripts/traced_buyer_run.py` with `--vertical hr_media` for production runs with full audit trails. This loads all 10 HR media research sections, synthesis prompts, and buyer scoring from config. Do not pass `--vertical home_services` or rely on defaults.

Run in batches of 4 — confirm after each batch before continuing. Respect Exa rate limits and backoff in `exa_client.py`. SAP SuccessFactors is already done and can be used as the reference output.
