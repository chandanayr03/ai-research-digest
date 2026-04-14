"""
Persistent storage for seen papers and user feedback.
JSON files committed back to repo by CI.
"""

import os
import json
import hashlib
from datetime import datetime
from config import MAX_SEEN_PAPERS, MAX_FEEDBACK_EVENTS

_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(_DIR, "seen_papers.json")
FEEDBACK_FILE = os.path.join(_DIR, "feedback.json")
SUBSCRIBERS_FILE = os.path.join(_DIR, "subscribers.json")


# ── Paper ID ──

def paper_id(paper: dict) -> str:
    """Generate a stable short ID for a paper."""
    link = paper.get("link", "")
    if "arxiv.org/abs/" in link:
        return link.split("arxiv.org/abs/")[-1].split("v")[0].strip()
    title = paper.get("title", "").lower().strip()
    return hashlib.sha1(title.encode()).hexdigest()[:16]


# ── Seen Papers ──

def load_seen() -> dict:
    """Load {paper_id: date_string} from disk."""
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_seen(seen: dict):
    """Save seen papers, trimming to max size."""
    if len(seen) > MAX_SEEN_PAPERS:
        items = sorted(seen.items(), key=lambda x: x[1])
        seen = dict(items[-MAX_SEEN_PAPERS:])
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


# ── Feedback Store ──

def _empty_feedback() -> dict:
    return {"last_update_id": 0, "papers": {}, "votes": []}


def load_feedback() -> dict:
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("last_update_id", 0)
                    data.setdefault("papers", {})
                    data.setdefault("votes", [])
                    return data
        except (json.JSONDecodeError, IOError):
            pass
    return _empty_feedback()


def save_feedback(store: dict):
    store["votes"] = store.get("votes", [])[-MAX_FEEDBACK_EVENTS:]
    papers = store.get("papers", {})
    if len(papers) > MAX_SEEN_PAPERS:
        items = sorted(papers.items(),
                       key=lambda x: x[1].get("last_seen", ""))
        store["papers"] = dict(items[-MAX_SEEN_PAPERS:])
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def record_vote(store: dict, pid: str, vote: str, user_id: str, username: str):
    """Record a thumbs up/down vote for a paper."""
    papers = store.setdefault("papers", {})
    entry = papers.get(pid, {"up": 0, "down": 0, "user_votes": {}})

    prev = entry.get("user_votes", {}).get(user_id)
    if prev == vote:
        return  # duplicate

    # Undo previous vote
    if prev == "up":
        entry["up"] = max(0, entry["up"] - 1)
    elif prev == "down":
        entry["down"] = max(0, entry["down"] - 1)

    # Apply new vote
    entry[vote] = entry.get(vote, 0) + 1
    entry.setdefault("user_votes", {})[user_id] = vote
    entry["last_seen"] = datetime.utcnow().isoformat()
    papers[pid] = entry

    store.setdefault("votes", []).append({
        "paper_id": pid, "vote": vote,
        "user_id": user_id, "username": username,
        "timestamp": datetime.utcnow().isoformat(),
    })


def build_preference_profile(store: dict, max_items: int = 6) -> dict:
    """Build liked/disliked lists from feedback for ranking prompts."""
    liked, disliked = [], []
    total = 0

    for pid, meta in store.get("papers", {}).items():
        if not isinstance(meta, dict):
            continue
        up = int(meta.get("up", 0))
        down = int(meta.get("down", 0))
        total += up + down
        if up + down == 0:
            continue
        score = up - down
        item = {"title": meta.get("title", pid), "score": score}
        if score > 0:
            liked.append(item)
        elif score < 0:
            disliked.append(item)

    liked.sort(key=lambda x: x["score"], reverse=True)
    disliked.sort(key=lambda x: x["score"])

    return {
        "total_votes": total,
        "liked": liked[:max_items],
        "disliked": disliked[:max_items],
    }


def register_paper(store: dict, paper: dict, topic: str, message_id=None):
    """Track a paper that was sent to Telegram."""
    pid = paper_id(paper)
    papers = store.setdefault("papers", {})
    entry = papers.get(pid, {"up": 0, "down": 0, "user_votes": {}})
    entry["title"] = paper.get("title", "")
    entry["topic"] = topic
    entry["link"] = paper.get("link", "")
    entry["last_seen"] = datetime.utcnow().isoformat()
    entry["message_id"] = message_id
    papers[pid] = entry


# ── Subscriber Preferences ──

def load_subscribers() -> dict:
    """Load {user_id: {topics: [list], username: str}}."""
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_subscribers(subs: dict):
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, indent=2)


def get_active_topics(subs: dict) -> set:
    """Get set of topic names that at least one subscriber wants."""
    topics = set()
    for user_data in subs.values():
        if isinstance(user_data, dict):
            for t in user_data.get("topics", []):
                topics.add(t)
    # If no subscribers yet, return all topics (default behavior)
    if not topics:
        from config import TOPICS
        return {t["name"] for t in TOPICS}
    return topics
