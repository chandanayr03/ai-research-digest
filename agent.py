"""
AI Research Digest Agent - ReAct-style autonomous loop.

PLAN -> SYNC FEEDBACK -> For each topic:
  SEARCH (arXiv + Semantic Scholar + Papers With Code)
  FILTER (skip seen + LLM relevance gate)
  DEDUP (fuzzy title matching)
  RANK (LLM picks top-k)
  SUMMARIZE (LLM 2-line summary)
-> DELIVER (Telegram, one paper per message + feedback buttons)
-> PERSIST (seen_papers.json + feedback.json)
"""

import sys
import traceback
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import config
import llm
import sources
import telegram
import storage


class DigestAgent:
    """Autonomous research paper digest agent."""

    def __init__(self):
        self.seen = storage.load_seen()
        self.feedback = storage.load_feedback()
        self.preferences = storage.build_preference_profile(self.feedback)
        self.new_seen = {}
        self.results = {}  # topic -> [(paper, summary), ...]

    def log(self, msg: str):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)

    # ── Phase 0: Sync feedback from Telegram ──

    def sync_feedback(self):
        self.log("PLAN: Syncing Telegram feedback...")
        try:
            last_id = self.feedback.get("last_update_id", 0)
            votes, new_last_id = telegram.pull_feedback(last_id)
            self.feedback["last_update_id"] = new_last_id

            for v in votes:
                storage.record_vote(
                    self.feedback, v["paper_id"], v["vote"],
                    v["user_id"], v["username"])

            storage.save_feedback(self.feedback)
            self.preferences = storage.build_preference_profile(self.feedback)
            self.log(f"  ACT: {len(votes)} new vote(s), "
                     f"{self.preferences['total_votes']} total")
        except Exception as e:
            self.preferences = {"total_votes": 0, "liked": [], "disliked": []}
            self.log(f"  OBSERVE: Feedback sync failed ({e}) - using neutral ranking")

    # ── Phase 1: Search all sources ──

    def search(self, topic: dict) -> list:
        name = topic["name"]
        cats = topic["arxiv_categories"]
        kws = topic["keywords"]
        collected = []

        for source_name, search_fn, args in [
            ("arXiv", sources.search_arxiv, (cats, kws, config.PAPERS_PER_SOURCE)),
            ("Semantic Scholar", sources.search_semantic_scholar, (kws, config.PAPERS_PER_SOURCE)),
            ("Papers With Code", sources.search_papers_with_code, (kws, config.PAPERS_PER_SOURCE)),
        ]:
            self.log(f"THINK: Searching {source_name} for '{name}'...")
            try:
                papers = search_fn(*args)
                self.log(f"  ACT: {source_name} -> {len(papers)} paper(s)")
                collected.extend(papers)
            except Exception as e:
                self.log(f"  OBSERVE: {source_name} failed ({e}) - continuing")

        return collected

    # ── Phase 2: Filter ──

    def filter_seen(self, papers: list, topic_name: str) -> list:
        fresh = []
        for p in papers:
            pid = storage.paper_id(p)
            if pid in self.seen:
                continue
            fresh.append(p)
            self.new_seen[pid] = datetime.utcnow().date().isoformat()
        self.log(f"  OBSERVE: {len(fresh)}/{len(papers)} are new for '{topic_name}'")
        return fresh

    def filter_relevant(self, papers: list, topic_name: str) -> list:
        relevant = []
        for p in papers:
            self.log(f"THINK: Relevance check - '{p['title'][:55]}...'")
            try:
                if llm.is_relevant(p["title"], p["abstract"], topic_name):
                    self.log("  ACT: RELEVANT")
                    relevant.append(p)
                else:
                    self.log("  ACT: OFF-TOPIC - discarded")
            except Exception as e:
                self.log(f"  OBSERVE: Check failed ({e}) - keeping")
                relevant.append(p)
        return relevant

    # ── Phase 3: Dedup ──

    @staticmethod
    def deduplicate(papers: list) -> list:
        if not papers:
            return []
        unique = [papers[0]]
        for p in papers[1:]:
            is_dup = False
            for existing in unique:
                sim = SequenceMatcher(None, p["title"].lower(),
                                      existing["title"].lower()).ratio()
                if sim > config.SIMILARITY_THRESHOLD:
                    # Merge metadata into existing
                    if p.get("citations") and not existing.get("citations"):
                        existing["citations"] = p["citations"]
                    if p.get("code_url") and not existing.get("code_url"):
                        existing["code_url"] = p["code_url"]
                    if p.get("trending"):
                        existing["trending"] = True
                    if existing["source"] != p["source"]:
                        existing["source"] += f" + {p['source']}"
                    is_dup = True
                    break
            if not is_dup:
                unique.append(p)
        return unique

    # ── Phase 4: Rank ──

    def rank(self, papers: list, topic_name: str) -> list:
        self.log(f"THINK: Deduplicating {len(papers)} papers...")
        unique = self.deduplicate(papers)
        self.log(f"  OBSERVE: {len(unique)} unique after dedup")

        if len(unique) <= config.TOP_K:
            return unique

        self.log(f"THINK: LLM ranking - picking top {config.TOP_K}...")
        try:
            indices = llm.rank(unique, topic_name, config.TOP_K, self.preferences)
            self.log(f"  ACT: Selected indices {indices}")
            return [unique[i] for i in indices]
        except Exception as e:
            self.log(f"  OBSERVE: Ranking failed ({e}) - using first {config.TOP_K}")
            return unique[:config.TOP_K]

    # ── Phase 5: Summarize ──

    def summarize(self, papers: list) -> list:
        results = []
        for p in papers:
            self.log(f"THINK: Summarizing '{p['title'][:55]}...'")
            try:
                summary = llm.summarize(p["title"], p["abstract"])
                self.log("  ACT: Summary ready")
                results.append((p, summary))
            except Exception as e:
                self.log(f"  OBSERVE: Summary failed ({e})")
                results.append((p, "Summary unavailable."))
        return results

    # ── Phase 6: Deliver ──

    def deliver(self):
        self.log("THINK: Delivering digest to Telegram...")
        today = datetime.utcnow().strftime("%B %d, %Y")
        telegram.send_message(f"*AI Research Digest - {today}*")

        total_sent = 0
        for topic_name, papers in self.results.items():
            if not papers:
                continue
            telegram.send_message(f"--- *{topic_name}* ---")
            for i, (paper, summary) in enumerate(papers, 1):
                pid = storage.paper_id(paper)
                result = telegram.send_paper(paper, summary, i, pid)
                if result.get("ok"):
                    storage.register_paper(self.feedback, paper, topic_name,
                                           result.get("message_id"))
                    total_sent += 1
                else:
                    self.log(f"  OBSERVE: Failed to send '{paper['title'][:40]}...'")

        if total_sent == 0:
            telegram.send_message("No new papers this cycle.")

        # AI Insight of the Day
        all_titles = []
        for papers in self.results.values():
            for paper, _ in papers:
                all_titles.append(paper["title"])

        if all_titles:
            self.log("THINK: Generating AI Insight of the Day...")
            try:
                insight = llm.generate_ai_insight(all_titles)
                telegram.send_message(f"\n---\n{insight}")
                self.log("  ACT: Insight sent!")
            except Exception as e:
                self.log(f"  OBSERVE: Insight generation failed ({e}) - skipping")

        storage.save_feedback(self.feedback)
        self.log(f"  ACT: Sent {total_sent} paper(s) with feedback buttons")

    # ── Main Loop ──

    def run(self):
        self.log("=" * 55)
        self.log("  AI RESEARCH DIGEST AGENT")
        self.log(f"  {len(config.TOPICS)} topics | "
                 f"{config.LOOKBACK_DAYS}-day window | "
                 f"top {config.TOP_K} per topic")
        self.log(f"  {len(self.seen)} papers in memory")
        self.log("=" * 55 + "\n")

        self.sync_feedback()
        print()

        import time

        for idx, topic in enumerate(config.TOPICS):
            name = topic["name"]
            self.log(f"=== [{idx+1}/{len(config.TOPICS)}] {name} ===")

            if idx > 0:
                self.log("  (5s pause between topics)")
                time.sleep(5)

            # Search
            raw = self.search(topic)

            # Filter seen
            fresh = self.filter_seen(raw, name) if raw else []

            # Self-correction: if all are seen, broaden search
            if not fresh and raw:
                self.log(f"REFLECT: All papers seen - broadening search...")
                broader = sources.search_arxiv(
                    topic["arxiv_categories"],
                    topic["keywords"][:2],
                    config.PAPERS_PER_SOURCE * 3)
                if broader:
                    fresh = self.filter_seen(broader, name)

            if not fresh:
                self.log(f"REFLECT: No new papers for '{name}' - skipping\n")
                self.results[name] = []
                continue

            # LLM relevance gate
            self.log(f"THINK: Relevance filtering {len(fresh)} paper(s)...")
            relevant = self.filter_relevant(fresh, name)
            if not relevant:
                self.log(f"REFLECT: None relevant for '{name}'\n")
                self.results[name] = []
                continue

            # Rank + Summarize
            top = self.rank(relevant, name)
            self.results[name] = self.summarize(top)
            self.log(f"REFLECT: '{name}' done - {len(self.results[name])} papers\n")

        # Deliver
        self.log("=== DELIVERING DIGEST ===")
        self.deliver()

        # Persist
        self.seen.update(self.new_seen)
        storage.save_seen(self.seen)
        self.log(f"ACT: Saved {len(self.new_seen)} new IDs "
                 f"(total: {len(self.seen)})")

        self.log("\nDONE - Agent finished successfully.")


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    agent = DigestAgent()
    try:
        agent.run()
    except Exception as e:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{ts}] FATAL: {e}\n{traceback.format_exc()}", flush=True)
        sys.exit(1)
