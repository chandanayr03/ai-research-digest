"""
Telegram integration - sending messages, collecting feedback, and topic subscriptions.
"""

import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ADMIN_USER_ID, TOPICS


def _api(method: str, **kwargs) -> dict:
    """Call Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        resp = requests.post(url, json=kwargs, timeout=15)
        return resp.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def send_message(text: str, reply_markup: dict = None, chat_id: str = None) -> dict:
    """Send a message to a chat. Returns {ok, message_id}."""
    payload = {
        "chat_id": chat_id or TELEGRAM_CHAT_ID,
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


def send_paper(paper: dict, summary: str, index: int, paper_id: str,
               difficulty: str = "", fun_fact: str = "") -> dict:
    """Send a single paper with difficulty tag, summary, fun fact, and feedback buttons."""
    trending = "  [TRENDING]" if paper.get("trending") else ""

    # Difficulty emoji
    diff_map = {
        "Beginner": "\U0001f7e2 Beginner",
        "Intermediate": "\U0001f7e1 Intermediate",
        "Advanced": "\U0001f534 Advanced",
    }
    diff_tag = diff_map.get(difficulty, "")

    lines = [f"*{index}. {paper['title']}*{trending}"]
    if diff_tag:
        lines.append(f"Difficulty: {diff_tag}")
    lines.append(paper["link"])
    if paper.get("code_url"):
        lines.append(f"Code: {paper['code_url']}")
    if paper.get("citations"):
        lines.append(f"Citations: {paper['citations']}")
    lines.append(f"\n{summary}")
    if fun_fact:
        lines.append(f"\n{fun_fact}")

    keyboard = {
        "inline_keyboard": [[
            {"text": "\U0001f44d Relevant", "callback_data": f"fb:up:{paper_id}"[:64]},
            {"text": "\U0001f44e Not useful", "callback_data": f"fb:down:{paper_id}"[:64]},
        ]]
    }
    return send_message("\n".join(lines), reply_markup=keyboard)


def send_subscribe_menu(chat_id: str, current_topics: list = None):
    """Send topic selection buttons to a user."""
    current = set(current_topics or [])
    topic_names = [t["name"] for t in TOPICS]

    buttons = []
    for name in topic_names:
        check = "\u2705 " if name in current else ""
        buttons.append([{
            "text": f"{check}{name}",
            "callback_data": f"sub:{name}"[:64],
        }])
    buttons.append([{"text": "\u2705 Subscribe to ALL", "callback_data": "sub:ALL"}])
    buttons.append([{"text": "\u274c Unsubscribe from ALL", "callback_data": "sub:NONE"}])

    send_message(
        "*Choose your topics:*\nTap to toggle. You'll only get papers for selected topics.",
        reply_markup={"inline_keyboard": buttons},
        chat_id=chat_id,
    )


def pull_feedback(last_update_id: int, subscribers: dict = None) -> tuple:
    """
    Fetch updates: feedback votes + subscription commands.
    Returns (votes_list, new_last_update_id).
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
    subs = subscribers or {}
    topic_names = [t["name"] for t in TOPICS]

    for update in body.get("result", []):
        uid = update.get("update_id", 0)
        if isinstance(uid, int):
            max_id = max(max_id, uid)

        # Handle /subscribe command
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        if text.lower() in ("/subscribe", "/start"):
            user = message.get("from") or {}
            user_id = str(user.get("id", ""))
            chat_id = str(message.get("chat", {}).get("id", ""))
            if user_id:
                current = subs.get(user_id, {}).get("topics", [])
                send_subscribe_menu(chat_id, current)
            continue

        # Handle subscription callbacks
        cb = update.get("callback_query") or {}
        data = cb.get("data", "")

        if data.startswith("sub:"):
            user = cb.get("from") or {}
            user_id = str(user.get("id", ""))
            username = user.get("username") or user.get("first_name") or "unknown"
            choice = data[4:]

            if user_id not in subs:
                subs[user_id] = {"topics": [], "username": username}

            if choice == "ALL":
                subs[user_id]["topics"] = topic_names[:]
                _answer_callback(cb.get("id", ""), f"Subscribed to all {len(topic_names)} topics!")
            elif choice == "NONE":
                subs[user_id]["topics"] = []
                _answer_callback(cb.get("id", ""), "Unsubscribed from all topics.")
            elif choice in topic_names:
                current = subs[user_id].get("topics", [])
                if choice in current:
                    current.remove(choice)
                    _answer_callback(cb.get("id", ""), f"Removed: {choice}")
                else:
                    current.append(choice)
                    _answer_callback(cb.get("id", ""), f"Added: {choice}")
                subs[user_id]["topics"] = current
            continue

        # Handle feedback callbacks
        parts = data.split(":", 2)
        if len(parts) != 3 or parts[0] != "fb" or parts[1] not in ("up", "down"):
            continue

        user = cb.get("from") or {}
        user_id = str(user.get("id", ""))

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
