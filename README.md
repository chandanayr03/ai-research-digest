# AI Research Digest Agent

An autonomous ReAct-style AI agent that curates the latest AI/ML research papers from multiple sources, filters and ranks them using an LLM, and delivers a clean digest to Telegram with feedback buttons.

## How It Works

```
SYNC FEEDBACK (Telegram votes from last run)
    |
    v
For each topic:
  SEARCH  ── arXiv + Semantic Scholar + Papers With Code
  FILTER  ── skip seen papers, then LLM relevance gate
  DEDUP   ── fuzzy title matching, merge metadata
  RANK    ── LLM picks top-k by novelty + impact + user feedback
  SUMMARIZE ── LLM 2-line summary per paper
    |
    v
DELIVER ── one paper per Telegram message + inline feedback buttons
PERSIST ── seen_papers.json + feedback.json
```

## Features

- **8 research topics** — LLMs, Computer Vision, AI Agents, ML/DL, Healthcare AI, NLP, Reinforcement Learning, Generative AI
- **3 data sources** — arXiv, Semantic Scholar, Papers With Code
- **Seen-paper memory** — never sends the same paper twice
- **LLM relevance gate** — filters off-topic papers using LLaMA 3.1
- **Fuzzy deduplication** — merges near-duplicates across sources
- **LLM ranking** — picks top papers by novelty, impact, and code availability
- **Feedback loop** — Telegram thumbs up/down buttons influence future rankings
- **Self-correction** — if all results are seen, automatically broadens the search
- **GitHub Actions** — runs every other day at 10:00 AM IST for free

## Architecture

```
You (Telegram)
  |
  v
DigestAgent (agent.py) ──── orchestrates everything
  |         |         |
  v         v         v
sources.py  llm.py    telegram.py
(arXiv,     (Groq/    (send msgs,
 S2, PWC)   LLaMA)    feedback)
  |
  v
storage.py (seen_papers.json, feedback.json)
```

| Component | Role |
|-----------|------|
| `agent.py` | **Agent** — plans, searches, filters, ranks, delivers |
| `llm.py` | **Model interface** — all Groq/LLaMA calls |
| `sources.py` | **Tools** — arXiv, Semantic Scholar, Papers With Code APIs |
| `telegram.py` | **Tool** — Telegram Bot API for delivery and feedback |
| `storage.py` | **Memory** — persistent seen papers and feedback state |
| `config.py` | **Config** — topics, API keys, settings |

## Quick Start

```bash
git clone https://github.com/chandanayr03/ai-research-digest.git
cd ai-research-digest

pip install -r requirements.txt

cp .env.example .env
# Fill in your API keys (see below)

python agent.py
```

## Getting API Keys

### Groq (Free)
1. Go to https://console.groq.com
2. Create an API key
3. Paste into `GROQ_API_KEY` in `.env`

### Telegram Bot
1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow prompts, copy the token → `TELEGRAM_BOT_TOKEN`
3. Send any message to your new bot
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Find `"chat":{"id":XXXXXXX}` → `TELEGRAM_CHAT_ID`

## GitHub Actions (Auto-Scheduling)

1. Push to GitHub
2. Go to **Settings → Secrets → Actions**
3. Add secrets: `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
4. The agent runs every other day automatically

## Configuration

Edit `config.py` to add/remove topics or change settings:

```python
# Add a new topic
{
    "name": "Robotics",
    "arxiv_categories": ["cs.RO"],
    "keywords": ["robot learning", "manipulation", "locomotion"],
},
```

| Setting | Default | Description |
|---------|---------|-------------|
| `PAPERS_PER_SOURCE` | 5 | Papers fetched per source per topic |
| `TOP_K` | 3 | Papers kept after ranking |
| `LOOKBACK_DAYS` | 2 | How far back to search |
| `GROQ_MODEL` | llama-3.1-8b-instant | LLM model to use |

## Project Structure

```
ai-research-digest/
├── agent.py              # Main agent loop (ReAct pattern)
├── config.py             # Settings and topic definitions
├── llm.py                # LLM interface (Groq/LLaMA)
├── sources.py            # Paper search APIs
├── telegram.py           # Telegram bot integration
├── storage.py            # Persistent state management
├── seen_papers.json      # Papers already sent (auto-updated)
├── feedback.json         # User feedback state (auto-updated)
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
├── .gitignore
├── .github/workflows/
│   └── digest.yml        # GitHub Actions cron job
└── README.md
```

## License

MIT

## Author

**Chandana Y R** — [GitHub](https://github.com/chandanayr03)
