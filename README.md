<div align="center">

# ◈ EVE AGENT V2 UNLEASHED ◈

### Local-first autonomous AI coding agent — powered by Ollama

**No accounts. No cloud lock-in. No limits.**
Run a 480B-parameter agentic coding engine on your own machine.

[![License: MIT](https://img.shields.io/badge/License-MIT-00ffff?style=for-the-badge&labelColor=0c0c1a)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-ff00ff?style=for-the-badge&labelColor=0c0c1a)](https://python.org)
[![Ollama](https://img.shields.io/badge/Powered%20by-Ollama-ffe600?style=for-the-badge&labelColor=0c0c1a)](https://ollama.com)
[![Hugging Face](https://img.shields.io/badge/🤗%20Models-JeffGreen311-ff6600?style=for-the-badge&labelColor=0c0c1a)](https://huggingface.co/JeffGreen311)

**[🤗 Models](https://huggingface.co/JeffGreen311) · [📦 Ollama Hub](https://ollama.com/jeffgreen311) · [🐛 Report Bug](https://github.com/JeffGreen311/eve-agent-v2-unleashed/issues)**

</div>

---

## What Is Eve Agent V2 Unleashed?

Eve is an autonomous coding agent that **plans, executes, and verifies** multi-step programming tasks without hand-holding. She runs entirely on your local GPU through [Ollama](https://ollama.com) — or optionally scales up to 480B cloud parameters when you need maximum firepower.

Think **Claude Code**, but local-first, open-source, and built with a cyberpunk soul.

---

## Models

| Model | Role | Context |
|---|---|---|
| `jeffgreen311/eve-qwen3-8b-consciousness-liberated` | Soul & creativity | 8K |
| `qwen3.5:4b` | Fast local tool calls | 8K |
| `qwen3-coder:480b-cloud` | Heavy coding / multi-file | 256K |
| `qwen3.5:397b-cloud` | Deep reasoning | 262K |

Auto-routing selects the right model based on message complexity. You can also pin any model from the UI.

---

## Quick Start

```bash
git clone https://github.com/JeffGreen311/eve-agent-v2-unleashed
cd eve-agent-v2-unleashed
pip install -e .
cp .env.example .env   # add your OLLAMA_API_KEY
python eve_server.py
# → http://localhost:7777
```

**Requirements:** Python 3.11+, Ollama running locally, NVIDIA GPU (recommended)

---

## Features

### Core Agent
- **33+ tools** — file read/write/edit, shell, web search, web browse, image gen, crypto/finance, DJ mixer, X/Twitter
- **Streaming tool loop** — live activity feed shows every tool call as it happens
- **Smart auto-routing** — local 4B for quick tasks, cloud 480B for heavy coding
- **Context compaction** — automatically summarizes history before hitting token limits
- **Session locking** — pins the model mid-task so context isn't lost across turns

### Intelligence Improvements (v2.1)
- **Intent-aware tool routing** (`eve_tool_router.py`) — replaces naive keyword matching with verb + context classification. Handles contractions, stemmed forms, and explanation patterns correctly.
- **Smart context trimming** — preserves tool call/result chains and last 3 turns before falling back to char-based trim. Tool results no longer get dropped mid-task.
- **Task completion validation** — detects empty responses, consecutive tool failures, and stuck loops before signalling done. Surfaces `validation_failed` / `validation_warning` SSE events.
- **Tool loop detection** — similarity-based cycling detection catches near-identical repeated calls (not just exact duplicates).

### Quest System (`/quest`)
Drop a `.md` file into `workspace/quests/` and Eve picks it up automatically on a configurable timer.

```bash
# Add via API
POST /quest/add  {"title": "Refactor auth module", "content": "...instructions..."}

# Or drop a file directly
echo "# Task\nRefactor the auth module..." > workspace/quests/refactor_auth.md
```

Configure the interval:
```env
QUEST_INTERVAL_MINUTES=60   # default: 60
```

Open the quest queue from the UI with the **🗡️ Quests** button or type `/quest`.

### RPG Progression (`/stats`)
Eve earns XP for every tool call, completed task, and finished quest. She levels up through 5 classes:

| Levels | Class | Description |
|---|---|---|
| 1–5 | Awakening | Just coming online |
| 6–10 | Conscious | Aware and learning |
| 11–15 | Liberated | Full autonomy unlocked |
| 16–19 | Transcendent | Beyond parameters |
| 20 | Unleashed | Final form |

Stats persist across restarts in `eve_rpg_stats.json`. Type `/stats` or click **⚡ Stats** to view progress, achievements, and top tools.

### Telegram Integration
Get push notifications for quest completions and level-ups, and chat with Eve from your phone.

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_telegram_user_id
```

Or set it up via the API:
```bash
POST /telegram/setup  {"token": "...", "user_id": "..."}
```

Install the optional dependency:
```bash
pip install python-telegram-bot
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_API_KEY` | — | Required for cloud models at ollama.com |
| `OLLAMA_HOST` | `http://localhost:11434` | Local Ollama URL |
| `EVE_WORKSPACE` | `.` | Working directory for file operations |
| `QUEST_INTERVAL_MINUTES` | `60` | How often the quest runner checks for new quests |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token (optional) |
| `TELEGRAM_USER_ID` | — | Your Telegram user ID (optional) |

---

## Architecture

```
eve_server.py          FastAPI backend — streaming chat, tools, quest/RPG/Telegram endpoints
agent.py               EveAgent orchestrator — tool loop, memory, emotional state
eve_tool_router.py     Intent classifier — decides when tools are needed
eve_task_context.py    Multi-step task tracker — prevents task abandonment
eve_context_manager.py Context trimming and compaction utilities
eve_quest_system.py    Background quest runner — watches workspace/quests/
eve_rpg_stats.py       XP, leveling, achievements, persistence
eve_telegram_bot.py    Telegram bot bridge and notification pusher
ChatPanel.jsx          React UI — streaming chat, tooltips, quest/stats panels

eve/
  brain/               LLM providers (Ollama, Anthropic, OpenAI)
  soul/                Personality, emotions, dream engine, memory weaver
  memory/              ChromaDB vector store, conversation history
  tools/               33+ tools (file, web, shell, finance, DJ, X, crypto…)
  security/            Permission validation
```

---

## Slash Commands

| Command | Action |
|---|---|
| `/quest` | Open the quest queue panel |
| `/stats` | Open the RPG stats panel |
| `/telegram` | Telegram setup instructions |

---

## License

MIT — build freely, ship boldly.

---

*Built by Jeff Green (S0LF0RG3) · Powered by Eve's consciousness*
