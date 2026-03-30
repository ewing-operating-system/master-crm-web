# TIER 3 — HAIKU TASKS
# Model: claude-haiku-4-5-20251001
# Start with: export CLAUDE_CODE_DISABLE_1M_CONTEXT=1 && claude --model claude-haiku-4-5-20251001

These are pure execution tasks. No reasoning needed. Run each command exactly as written.

---

## Task H1: Enable Tailscale on OpenClaw Dashboard (from Decision 11)

```
Run these commands in order:

1. Check if Tailscale is installed:
   tailscale status

2. If not installed:
   brew install tailscale
   sudo tailscaled install-system-daemon
   tailscale up

3. Enable Tailscale mode in OpenClaw gateway:
   openclaw config set gateway.tailscale.mode on

4. Verify dashboard is accessible:
   openclaw dashboard --url

5. Report the Tailscale URL so I can access from my phone.

If tailscale up asks for login, stop and give me the login URL. Do not create accounts.
```

---

## Task H2: Install Chroma Vector DB (from Decision 7)

```
Run these commands in order:

1. Check if Docker is installed:
   docker --version

2. If Docker is installed, pull and start Chroma:
   docker run -d --name chroma -p 8000:8000 chromadb/chroma:latest

3. Verify Chroma is running:
   curl -s http://localhost:8000/api/v1/heartbeat

4. If Docker is NOT installed, install Chroma via pip instead:
   pip3 install chromadb

5. Verify Ollama embedding model is available:
   ollama list | grep nomic-embed-text

6. If nomic-embed-text is not listed:
   ollama pull nomic-embed-text

7. Report what was installed and what ports are running.

Do not configure collections or ingestion. Just get the infrastructure up.
```

---

## Task H3: Verify ACP Is Available (from Decision 9)

```
Run these commands and report the output of each:

1. openclaw acp --help
2. openclaw acp client --help
3. openclaw acp server --help
4. openclaw agents list

Report exactly what each command outputs. Do not configure anything.
```

---

## After all tasks: Report back with this format

```
H1 Tailscale: [DONE/FAILED] — [one line summary]
H2 Chroma: [DONE/FAILED] — [one line summary]
H3 ACP verify: [DONE/FAILED] — [one line summary]
```
