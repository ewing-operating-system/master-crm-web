# Page System v2 Architecture — saved from opus-architect session 2026-03-30

See full design in conversation context. Key decisions:
- Jinja2 template engine (already in stack)
- page_registry + page_versions + entity_themes tables in Supabase
- CSS custom properties for entity theming (AND=black, RevsUp=red)
- Vercel preview branches for staging
- Separate client-view files (not query params)
- Activity feed table with DB triggers
- Orchestrator with Claude→DeepSeek→Gemini→static fallback chain
- 5-phase migration plan (~25-30 hours agent work)
