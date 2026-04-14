"""
LLM interface - all Groq/LLaMA calls go through here.
Single responsibility: talk to the model and return text.
"""

import time
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL

_client = Groq(api_key=GROQ_API_KEY)


def ask(prompt: str, max_tokens: int = 300, temperature: float = 0.5) -> str:
    """Send a prompt to Groq and return the response text. Retries on failure."""
    for attempt in range(3):
        try:
            resp = _client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err = str(e).lower()
            if "401" in err or "invalid_api_key" in err or "authentication" in err:
                raise RuntimeError(f"Groq auth failed - check GROQ_API_KEY: {e}")
            if "429" in err or "rate_limit" in err:
                print(f"  [rate-limited] waiting 15s...")
                time.sleep(15)
                continue
            if attempt == 2:
                raise
            print(f"  [retry] Groq call failed: {e}")
            time.sleep(3)
    return ""


def is_relevant(title: str, abstract: str, topic: str) -> bool:
    """Ask LLM if a paper belongs to the given topic."""
    prompt = f"""You are a strict AI/ML research curator.

Topic: "{topic}"
Paper: {title}
Abstract (first 300 chars): {abstract[:300]}

Is this paper genuinely relevant to the topic? Answer exactly: YES or NO"""
    answer = ask(prompt, max_tokens=5, temperature=0.0)
    return answer.strip().upper().startswith("Y")


def rank(papers: list, topic: str, top_k: int, feedback: dict = None) -> list:
    """Ask LLM to pick top-k papers by novelty and impact. Returns indices."""
    if len(papers) <= top_k:
        return list(range(len(papers)))

    lines = []
    for i, p in enumerate(papers):
        tags = []
        if p.get("citations"):
            tags.append(f"citations={p['citations']}")
        if p.get("code_url"):
            tags.append("has-code")
        if p.get("trending"):
            tags.append("TRENDING")
        meta = f" ({', '.join(tags)})" if tags else ""
        lines.append(f"[{i}] \"{p['title']}\"{meta}\n    {p['abstract'][:200]}...")

    feedback_block = ""
    if feedback and feedback.get("total_votes", 0) > 0:
        liked = "\n".join(f"  - {x['title']}" for x in feedback.get("liked", [])[:6]) or "  - none"
        disliked = "\n".join(f"  - {x['title']}" for x in feedback.get("disliked", [])[:6]) or "  - none"
        feedback_block = f"""
User feedback signal (soft preference, don't override quality):
Liked:\n{liked}
Disliked:\n{disliked}
"""

    prompt = f"""You are an AI research curator. Pick the {top_k} MOST important papers on "{topic}".
Criteria: novelty, practical impact, scientific quality. Prefer papers with code or high citations.
Trending papers should rank higher. Also prefer papers from major AI labs (OpenAI, DeepMind, Google, Anthropic, Meta).
{feedback_block}
Papers:
{chr(10).join(lines)}

Return ONLY a JSON array of indices. Example: [2, 0, 5]
No explanation."""

    import json
    raw = ask(prompt, max_tokens=100, temperature=0.2).strip()
    start, end = raw.find("["), raw.rfind("]") + 1
    if start != -1 and end > start:
        indices = json.loads(raw[start:end])
        return [i for i in indices if isinstance(i, int) and 0 <= i < len(papers)][:top_k]
    return list(range(top_k))


def summarize(title: str, abstract: str) -> str:
    """Generate a tight 2-line summary of a paper."""
    prompt = f"""You are a research digest writer for AI/ML practitioners.

Paper: {title}
Abstract: {abstract}

Write EXACTLY 2 lines:
Line 1 - Core contribution (1 sentence)
Line 2 - Why it matters to practitioners (1 sentence)

No bullet points, no labels, no filler."""
    return ask(prompt, max_tokens=200, temperature=0.3)


def rate_difficulty(title: str, abstract: str) -> str:
    """Rate paper difficulty for readers."""
    prompt = f"""You are an AI research curator rating paper difficulty for a general tech audience.

Paper: {title}
Abstract (first 400 chars): {abstract[:400]}

Rate this paper's difficulty. Pick EXACTLY one:
- "Beginner" if someone with basic ML knowledge can understand it
- "Intermediate" if it requires solid ML/DL background
- "Advanced" if it requires deep expertise in the specific subfield

Reply with ONLY one word: Beginner, Intermediate, or Advanced"""
    answer = ask(prompt, max_tokens=5, temperature=0.0).strip()
    for level in ["Beginner", "Intermediate", "Advanced"]:
        if level.lower() in answer.lower():
            return level
    return "Intermediate"


def generate_topic_fact(topic_name: str) -> str:
    """Generate a fun 'Did You Know?' fact related to a specific topic."""
    prompt = f"""You are a fun AI newsletter writer.

Topic: "{topic_name}"

Write ONE "Did You Know?" fact about this AI/ML topic that is:
1. A real, verified historical or recent fact (NOT made up)
2. Surprising, fun, or counterintuitive
3. Short - max 2 sentences

Format exactly (include emoji):
Did you know? [your fact]

No intro, no outro. Just the fact."""
    return ask(prompt, max_tokens=100, temperature=0.8)


def generate_ai_insight(paper_titles: list) -> str:
    """Generate a fun, surprising AI fact/insight related to today's papers."""
    titles_block = "\n".join(f"- {t}" for t in paper_titles[:10])
    prompt = f"""You are a witty AI newsletter writer. Today's research digest covered these papers:

{titles_block}

Based on the themes in these papers, write ONE short "AI Insight of the Day" that is:
1. A real, verified fact about AI/ML (not made up)
2. Surprising or counterintuitive
3. Written in a fun, conversational tone
4. Related to recent AI evolution or a historical AI milestone

Format exactly like this (include the emoji):
🧠 AI Insight: [your fact here]

Keep it to 2-3 sentences max. Make it something people would want to share."""
    return ask(prompt, max_tokens=150, temperature=0.7)
