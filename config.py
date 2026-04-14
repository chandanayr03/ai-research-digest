"""
Configuration for AI Research Digest Agent.
All settings loaded from environment variables or .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "").strip()

# ── Agent Settings ──
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
PAPERS_PER_SOURCE = int(os.getenv("PAPERS_PER_SOURCE", 5))
TOP_K = int(os.getenv("TOP_K", 1))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", 2))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.75))

# ── Storage Limits ──
MAX_SEEN_PAPERS = 3000
MAX_FEEDBACK_EVENTS = 5000

# ── Research Topics ──
TOPICS = [
    {
        "name": "LLMs & Language Models",
        "arxiv_categories": ["cs.CL", "cs.AI"],
        "keywords": [
            "large language model", "LLM", "transformer",
            "instruction tuning", "RLHF", "RAG", "chain of thought",
            "Anthropic", "Claude", "OpenAI", "GPT", "Gemini", "LLaMA",
        ],
    },
    {
        "name": "Computer Vision",
        "arxiv_categories": ["cs.CV"],
        "keywords": [
            "image generation", "diffusion model", "object detection",
            "vision transformer", "CLIP", "image segmentation",
        ],
    },
    {
        "name": "AI Agents & Autonomous Systems",
        "arxiv_categories": ["cs.AI", "cs.MA"],
        "keywords": [
            "AI agent", "autonomous agent", "multi-agent",
            "tool use", "planning", "reasoning agent", "agentic",
        ],
    },
    {
        "name": "ML / DL Innovations",
        "arxiv_categories": ["cs.LG", "stat.ML"],
        "keywords": [
            "deep learning", "neural network", "optimization",
            "self-supervised", "foundation model", "scaling law",
        ],
    },
    {
        "name": "AI for Healthcare",
        "arxiv_categories": ["cs.AI", "q-bio.QM"],
        "keywords": [
            "medical imaging", "clinical NLP", "drug discovery",
            "healthcare AI", "biomedical", "pathology",
        ],
    },
    {
        "name": "NLP & Text Processing",
        "arxiv_categories": ["cs.CL"],
        "keywords": [
            "text classification", "sentiment analysis", "summarization",
            "question answering", "named entity recognition", "machine translation",
        ],
    },
    {
        "name": "Reinforcement Learning",
        "arxiv_categories": ["cs.LG", "cs.AI"],
        "keywords": [
            "reinforcement learning", "reward model", "policy optimization",
            "multi-agent RL", "offline RL", "RLHF",
        ],
    },
    {
        "name": "Generative AI",
        "arxiv_categories": ["cs.CV", "cs.LG"],
        "keywords": [
            "diffusion model", "GAN", "image synthesis",
            "text to image", "video generation", "stable diffusion",
        ],
    },
]
