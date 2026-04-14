"""
Telegram integration - sending messages and collecting feedback.
"""

import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ADMIN_USER_ID


def _api(method: str, **kwargs) -> dict:
    """Call Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        resp = requests.post(url, json=kwargs, timeout=15)
        return resp.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def send_message(text: str, reply_markup: dict = None) -> dict:
    """Send a message to the configured chat. Returns {ok, message_id}."""
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    result = _api("sendMessage", **payload)

    if result.get("ok"):
        return {"ok": True, "message_id": result["result"].get("message_id")}

    # Retry without markdown if formatting failed
    payload.pop("parse_mode")
    payload["text"] = text.replace("*", "").replace("_", "").replace("`", "")
    result = _api("sendMessage", **payload)
    if result.get("ok"):
        return {"ok": True, "message_id": result["result"].get("message_id")}

    return {"ok": False, "error": result.get("description", "unknown")}


def send_paper(paper: dict, summary: str, index: int, paper_id: str) -> dict:
    """Send a single paper with feedback buttons."""
    trending = "  [TRENDING]" if paper.get("trending") else ""
    lines = [
        f"*{index}. {paper['title']}*{trending}",
        paper["link"],
    ]
    if paper.get("code_url"):
        lines.append(f"Code: {paper['code_url']}")
    if paper.get("citations"):
        lines.append(f"Citations: {paper['citations']}")
    lines.append(f"\n{summary}")

    keyboard = {
        "inline_keyboard": [[
            {"text": "\U0001f44d Relevant", "callback_data": f"fb:up:{paper_id}"[:64]},
            {"text": "\U0001f44e Not useful", "callback_data": f"fb:down:{paper_id}"[:64]},
        ]]
    }
    return send_message("\n".join(lines), reply_markup=keyboard)


def pull_feedback(last_update_id: int) -> tuple:
    """
    Fetch new callback query updates from Telegram.
    Returns (votes_list, new_last_update_id).
    Each vote: {paper_id, vote, user_id, username, callback_id}
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        resp = requests.get(url, params={"offset": last_update_id + 1, "timeout": 0},
                            timeout=30)
        resp.raise_for_status()
        body = resp.json()
    except Exception:
        return [], last_update_id

    if not body.get("ok"):
        return [], last_update_id

    votes = []
    max_id = last_update_id

    for update in body.get("result", []):
        uid = update.get("update_id", 0)
        if isinstance(uid, int):
            max_id = max(max_id, uid)

        cb = update.get("callback_query") or {}
        data = cb.get("data", "")
        parts = data.split(":", 2)
        if len(parts) != 3 or parts[0] != "fb" or parts[1] not in ("up", "down"):
            continue

        user = cb.get("from") or {}
        user_id = str(user.get("id", ""))

        # Admin-only gate
        if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
            _answer_callback(cb.get("id", ""), "Feedback restricted to admin.")
            continue

        votes.append({
            "paper_id": parts[2],
            "vote": parts[1],
            "user_id": user_id,
            "username": user.get("username") or user.get("first_name") or "unknown",
            "callback_id": cb.get("id", ""),
        })
        _answer_callback(cb.get("id", ""), "Thanks for the feedback!")

    return votes, max_id


def _answer_callback(callback_id: str, text: str):
    if callback_id:
        _api("answerCallbackQuery", callback_query_id=callback_id,
             text=text, show_alert=False)
