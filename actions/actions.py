from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType, FollowupAction, ActiveLoop
import urllib.parse
import re
import string
import mysql.connector
from mysql.connector.connection import MySQLConnection
from urllib.parse import quote_plus
from html import escape

# -------------------------------------------------------------------
# Shared data / constants
# -------------------------------------------------------------------

ALIASES = {
    "recliner": "Recliner Seat",
    "bookshelf": "Bookshelf Classic",
    "queen bed": "Queen Bed Frame",
}
# Canonical product names
CANON = {
    "ergo chair": "Ergo Chair",
    "coffee table": "Coffee Table",
    "tv console": "TV Console",
    "bookshelf classic": "Bookshelf Classic",
    "queen bed frame": "Queen Bed Frame",
    "recliner seat": "Recliner Seat",
}

#generic words
GENERIC_WORDS = {
    "manual", "instructions", "instruction", "guide", "assembly",
    "please", "pls", "for", "the", "a", "an",
    "can", "you", "me", "my", "need", "want", "get", "show", "i"
}

# example orders
mock_orders = {
    "12345": {"status": "processing"},
    "56789": {"status": "shipped"},
    "987654": {"status": "processing"},
    "23057": {"status": "shipped"},
    "23058": {"status": "delivered"},
}

#DB connection
def _connect() -> MySQLConnection:
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="luxfurn",
    )

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _send_lines_as_html(dispatcher: CollectingDispatcher, lines: List[str]) -> None:
    """
    Send a single chat bubble with visible line breaks.
    Escapes content to avoid HTML injection, then uses <br> to force newlines.
    """
    msg_html = "<br>".join(escape(line) for line in lines)
    dispatcher.utter_message(text=msg_html)

# -------------------------------------------------------------------
# Existing actions (keep these as-is for your teammates)
# -------------------------------------------------------------------
def _get_username(tracker: Tracker) -> Optional[str]:
    sid = (tracker.sender_id or "").strip()

    # Debug print to see raw value
    print(f"### DEBUG _get_username RAW sender_id='{sid}'")

    if sid and sid.lower() != "guest":
        normalized = sid.split("|")[-1].strip()
        print(f"### DEBUG _get_username USING normalized='{normalized}'")
        return normalized

    # No sender_id or it's 'guest'
    return None

def _eta_days_from_status(status: str) -> Optional[int]:
    s = (status or "").lower()
    if s == "pending":
        return 5
    if s == "processing":
        return 3
    if s == "shipped":
        return 2
    if s in ("out_for_delivery", "out for delivery"):
        return 1
    if s == "delivered":
        return 0
    if s in ("cancelled", "canceled"):
        return None
    return None

class ActionPickOrderForCancel(Action):
    def name(self) -> Text:
        return "action_pick_order_for_cancel"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        username = _get_username(tracker)
        if not username:
            dispatcher.utter_message("Please log in to cancel orders.")
            return []

        conn = cur = None
        try:
            conn = _connect()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT order_id, order_status
                FROM orders
                WHERE username = %s
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (username,),
            )
            rows = cur.fetchall()

            if not rows:
                dispatcher.utter_message("I couldn’t find any orders on your account.")
                return []

            # If exactly one order, auto-pick and confirm (unless not cancellable)
            if len(rows) == 1:
                oid = str(rows[0]["order_id"])
                status = rows[0]["order_status"]
                _send_lines_as_html(dispatcher, [f"You have 1 order on file: Order #{oid} — {status}."])
                if (status or "").lower() in ("cancelled", "canceled", "delivered"):
                    _send_lines_as_html(dispatcher, [f"Order #{oid} cannot be cancelled (current status: {status})."])
                    return [SlotSet("cancel_context", False), SlotSet("info_context", False)]
                return [
                    SlotSet("order_id", oid),
                    SlotSet("cancel_context", True),
                    SlotSet("info_context", False),
                    FollowupAction("utter_confirm_cancel"),
                ]

            # Otherwise, list orders and ask which to cancel
            lines = ["Your Orders:"]
            for r in rows:
                lines.append(f"- Order #{r['order_id']} — {r['order_status']}")
            _send_lines_as_html(dispatcher, lines)
            dispatcher.utter_message(response="utter_ask_which_order_cancel")
            return [SlotSet("cancel_context", True), SlotSet("info_context", False)]

        except Exception as e:
            print("DB error pick-for-cancel:", e)
            dispatcher.utter_message("Sorry, I couldn’t fetch your orders right now.")
            return []
        finally:
            try:
                if cur: cur.close()
                if conn and conn.is_connected(): conn.close()
            except Exception:
                pass


class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        username = _get_username(tracker)
        order_id = tracker.get_slot("order_id")

        if not username:
            dispatcher.utter_message("Please log in to cancel orders.")
            return []
        if not order_id:
            dispatcher.utter_message("I need your order ID to cancel your order.")
            return []

        conn = cur = None
        try:
            conn = _connect()
            cur = conn.cursor(dictionary=True)

            # Ownership + current status check
            cur.execute(
                """
                SELECT order_status
                FROM orders
                WHERE order_id = %s AND username = %s
                """,
                (order_id, username),
            )
            row = cur.fetchone()
            if not row:
                dispatcher.utter_message(response="utter_no_order_found")
                return [SlotSet("order_id", None)]

            status = (row["order_status"] or "").lower()
            if status in ("delivered", "cancelled", "canceled"):
                _send_lines_as_html(dispatcher, [f"Order #{order_id} cannot be cancelled (current status: {row['order_status']})."])
                return [SlotSet("order_id", None), SlotSet("cancel_context", False)]

            # Perform cancel
            cur.execute(
                """
                UPDATE orders
                SET order_status = 'cancelled', updated_at = NOW()
                WHERE order_id = %s AND username = %s
                """,
                (order_id, username),
            )
            conn.commit()

            _send_lines_as_html(dispatcher, [f"Order #{order_id} has been cancelled."])
            return [
                SlotSet("order_id", None),
                SlotSet("cancel_context", False),
                FollowupAction("action_listen"),
            ]
        except Exception as e:
            print("DB error cancel:", e)
            dispatcher.utter_message("Sorry, I couldn’t cancel that order right now.")
            return []
        finally:
            try:
                if cur: cur.close()
                if conn and conn.is_connected(): conn.close()
            except Exception:
                pass

class ActionPickOrderForInfo(Action):
    def name(self) -> Text:
        return "action_pick_order_for_info"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        username = _get_username(tracker)
        if not username:
            dispatcher.utter_message("Please log in to view your orders.")
            return []

        conn = cur = None
        try:
            conn = _connect()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT order_id, order_status
                FROM orders
                WHERE username = %s
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (username,),
            )
            rows = cur.fetchall()

            if not rows:
                dispatcher.utter_message("I couldn’t find any orders on your account.")
                return []

            if len(rows) == 1:
                oid = str(rows[0]["order_id"])
                _send_lines_as_html(dispatcher, [f"You have 1 order on file: Order #{oid} — {rows[0]['order_status']}."])
                return [
                    SlotSet("order_id", oid),
                    SlotSet("info_context", True),
                    SlotSet("cancel_context", False),
                    FollowupAction("action_order_details"),
                ]

            lines = ["Your Orders:"]
            for r in rows:
                lines.append(f"- Order #{r['order_id']} — {r['order_status']}")
            _send_lines_as_html(dispatcher, lines)
            dispatcher.utter_message(response="utter_ask_which_order_status")
            return [
                SlotSet("info_context", True),
                SlotSet("cancel_context", False),
                FollowupAction("action_listen"),
            ]

        except Exception as e:
            print("DB error pick-for-info:", e)
            dispatcher.utter_message("Sorry, I couldn’t fetch your orders right now.")
            return []
        finally:
            try:
                if cur: cur.close()
                if conn and conn.is_connected(): conn.close()
            except Exception:
                pass


class ActionOrderDetails(Action):
    def name(self) -> Text:
        return "action_order_details"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        username = _get_username(tracker)
        order_id = tracker.get_slot("order_id")

        if not username:
            dispatcher.utter_message("Please log in to check your order.")
            return []
        if not order_id:
            dispatcher.utter_message("I need your order ID.")
            return []

        conn = cur = None
        try:
            conn = _connect()
            cur = conn.cursor(dictionary=True)

            # Header (ownership enforced)
            cur.execute(
                """
                SELECT order_id, order_status, total_amount, created_at,
                       shipping_address, shipping_city, shipping_state, shipping_zip
                FROM orders
                WHERE order_id = %s AND username = %s
                """,
                (order_id, username),
            )
            head = cur.fetchone()
            if not head:
                dispatcher.utter_message(response="utter_no_order_found")
                return [SlotSet("order_id", None)]

            # Items
            cur.execute(
                """
                SELECT furniture_name, unit_price, quantity, total_price
                FROM order_items
                WHERE order_id = %s
                ORDER BY item_id ASC
                """,
                (order_id,),
            )
            items = cur.fetchall()

            status = head["order_status"]
            eta = _eta_days_from_status(status)

            # Build message (one field per line, no markdown **)
            lines = [
                f"Order #{order_id} - Status: {status}",
                f"Placed: {head.get('created_at')}",
                f"Total: ${float(head.get('total_amount') or 0):.2f}",
                f"Ship to: {head.get('shipping_address')}, {head.get('shipping_city')}, {head.get('shipping_state')} {head.get('shipping_zip')}",
            ]

            if items:
                lines.append("Items:")
                for it in items:
                    lines.append(f"• {it['furniture_name']} × {it['quantity']} — ${float(it['total_price']):.2f}")

            if eta is None:
                if str(status).lower() == "delivered":
                    lines.append("ETA: Delivered.")
                elif str(status).lower() in ("cancelled", "canceled"):
                    lines.append("ETA: Cancelled (will not be delivered).")
                else:
                    lines.append("ETA: Not available.")
            elif eta == 0:
                lines.append("ETA: Today.")
            elif eta == 1:
                lines.append("ETA: 1 day.")
            else:
                lines.append(f"ETA: {eta} days.")

            _send_lines_as_html(dispatcher, lines)
            return [
                SlotSet("info_context", False),
                SlotSet("order_id", None),
                FollowupAction("action_listen"),
            ]
        except Exception as e:
            print("DB error details:", e)
            dispatcher.utter_message("Sorry, I couldn’t fetch that order right now.")
            return []
        finally:
            try:
                if cur: cur.close()
                if conn and conn.is_connected(): conn.close()
            except Exception:
                pass


class SubmitFeedbackForm(Action):
    def name(self) -> str:
        return "action_store_feedback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[str, Any]) -> List[Dict[str, Any]]:

        feedback = tracker.get_slot("feedback_text")
        print("Collected feedback:", feedback)
        print("All slots:", tracker.slots)

        return [SlotSet("feedback_text", None),
                SlotSet("requested_slot", None),
                ActiveLoop(None)]

class ActionStoreFeedback(Action):
    def name(self) -> str:
        return "action_store_feedback"

    def run(self, dispatcher, tracker, domain):
        rating = tracker.get_slot("feedback_rating")
        text = tracker.get_slot("feedback_text")

        sender_id = tracker.sender_id or ""
        # Guard against missing pipe to avoid ValueError
        if "|" in sender_id:
            user_id, username = sender_id.split("|", 1)
        else:
            user_id, username = sender_id, ""

        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="luxfurn"
        )
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO chatbot_reviews (user_id, rating, comment)
            VALUES (%s, %s, %s)
            """,
            (user_id, rating, text)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return []


# -------------------------------------------------------------------
# NEW (grouped): Manual search helpers & actions
# -------------------------------------------------------------------

BASE_MANUAL_URL = (
    "http://localhost/FYP-25-S2-34-Chatbot/Src/Boundary/Customer/CustomerInstructionManualUI.php"
)

def _manual_link_from_query(raw_query: str) -> str:
    """Build the manual search link with the user's query."""
    return f"{BASE_MANUAL_URL}?q={urllib.parse.quote(raw_query)}"

def _normalize_name(text: Optional[str]) -> Optional[str]:
    """Map free text to a canonical product name using CANON + ALIASES."""
    if not text:
        return None
    names = {**CANON, **ALIASES}
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    tokens = [w for w in t.split() if w and w not in GENERIC_WORDS]
    if not tokens:
        return None
    s = " ".join(tokens)
    for k in sorted(names.keys(), key=len, reverse=True):
        if k in s:
            return names[k]
    for tok in tokens:
        if tok in names:
            return names[tok]
    return None

def _extract_product(raw_text: str, entities: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Resolve a product from latest message via entity → regex → normalization."""
    for e in (entities or []):
        if e.get("entity") == "furniture_name" and e.get("value"):
            n = _normalize_name(e["value"])
            if n:
                return n
    names = {**CANON, **ALIASES}
    pattern = r"\b(?:%s)\b" % "|".join(re.escape(k) for k in names.keys())
    m = re.search(pattern, raw_text.lower())
    if m:
        return names[m.group(0)]
    return _normalize_name(raw_text)

def _is_generic_manual_query(text: str) -> bool:
    """True if the message contains no meaningful product tokens."""
    tokens = [w for w in re.findall(r"\w+", (text or "").lower()) if w]
    non_generic = [w for w in tokens if w not in GENERIC_WORDS]
    return len(non_generic) == 0

def _extract_keyword(text: str) -> str:
    """Fallback: pick a useful keyword/phrase from text (e.g., 'recliner')."""
    tokens = [w for w in re.findall(r"\w+", (text or "").lower()) if w and w not in GENERIC_WORDS]
    if not tokens:
        return ""
    # prefer last 2 tokens if multiword (e.g., 'dining chair'), else last token
    tail = tokens[-2:] if len(tokens) >= 2 else tokens[-1:]
    return " ".join(tail).strip()

def _send_clickable_link(dispatcher: CollectingDispatcher, title: str, link: str) -> None:

    html_text = (
        f'{title}:<br>'
        f'<a href="{link}" target="_blank" rel="noopener noreferrer">Open manual search</a><br>'
        f'{link}'
    )
    dispatcher.utter_message(text=html_text)

class ActionGetManual(Action):
    def name(self) -> Text:
        return "action_get_manual"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        import string

        raw = tracker.latest_message.get("text") or ""
        raw_query = raw.strip().strip(string.punctuation)

        # 1) Try to resolve a known product (incl. aliases) from THIS message
        canonical = _extract_product(raw, tracker.latest_message.get("entities"))

        if canonical:
            link = _manual_link_from_query(canonical)
            _send_clickable_link(dispatcher, f"Here’s the instruction manual search for <b>{canonical}</b>", link)
            return [SlotSet("manual_furniture", canonical)]

        # 2) If it's totally generic, ask which item
        if _is_generic_manual_query(raw_query):
            try:
                dispatcher.utter_message(response="utter_ask_manual_furniture")
            except Exception:
                dispatcher.utter_message(text="Which furniture item do you need the instruction manual for?")
            return [SlotSet("manual_furniture", None)]

        # 3) Otherwise, use a keyword from their text (e.g., 'recliner' from 'assembly guide for recliner')
        keyword = _extract_keyword(raw_query)
        link = _manual_link_from_query(keyword or raw_query)
        _send_clickable_link(dispatcher, f"Here’s the instruction manual search for <b>{keyword or raw_query}</b>", link)
        return [SlotSet("manual_furniture", keyword or None)]

class ActionResetManualSlot(Action):
    def name(self) -> Text:
        return "action_reset_manual_slot"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        return [SlotSet("manual_furniture", None)]

class ActionCreateSupportTicket(Action):
    def name(self) -> Text:
        return "action_create_support_ticket"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        subject = (tracker.get_slot("ticket_subject") or "").strip()
        message = (tracker.get_slot("ticket_message") or "").strip()

        # Expect sender_id to look like "123|username" (you already use this pattern)
        user_id = None
        try:
            sender_id = tracker.sender_id or ""
            parts = sender_id.split("|", 1)
            if parts and parts[0].strip().isdigit():
                user_id = int(parts[0].strip())
        except Exception:
            user_id = None

        if not user_id:
            dispatcher.utter_message(text="Please log in to create a support ticket.")
            return []

        if not subject or not message:
            dispatcher.utter_message(text="I need both a subject and a brief description to file your ticket.")
            return []

        conn = cur = None
        try:
            conn = _connect()
            cur = conn.cursor()

            cur.execute("""
                SELECT u.id AS admin_id, COALESCE(COUNT(t.id), 0) AS load_count
                FROM support_ticket_roles r
                JOIN users u
                  ON u.username = r.username
                 AND u.role = 'admin'
                 AND u.status = 1
                LEFT JOIN support_tickets t
                  ON t.assigned_admin_id = u.id
                 AND t.status IN ('open','responded')
                WHERE r.active = 1
                GROUP BY u.id
                ORDER BY load_count ASC, u.id ASC
                LIMIT 1
            """)
            row = cur.fetchone()
            assigned_admin_id = row[0] if row else None

            cur.execute(
                """
                INSERT INTO support_tickets (user_id, subject, message, assigned_admin_id)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, subject, message, assigned_admin_id),
            )
            conn.commit()

            # get the new ticket id
            ticket_id = cur.lastrowid

            dispatcher.utter_message(response="utter_ticket_created", ticket_id=ticket_id)
            return [
                SlotSet("ticket_subject", None),
                SlotSet("ticket_message", None),
            ]
        except Exception as e:
            print("DB error create ticket:", e)
            dispatcher.utter_message(response="utter_ticket_error")
            return []
        finally:
            try:
                if cur: cur.close()
                if conn and conn.is_connected(): conn.close()
            except Exception:
                pass

class ActionShowFurnitureRecommendations(Action):
    def name(self) -> Text:
        return "action_show_furniture_recommendations"

    def _extract_query(self, tracker: Tracker) -> Optional[str]:
        # Prefer an extracted entity if you use one
        ents = tracker.latest_message.get("entities", []) or []
        for e in ents:
            if e.get("entity") in {"product_name", "furniture", "search_term"}:
                val = (e.get("value") or "").strip()
                if val:
                    return val

        # Fallback: use the raw user text minus common lead-in phrases
        text = (tracker.latest_message.get("text") or "").strip()
        if not text:
            return None

        # Strip simple prefixes like "I'm looking for", "show me", "find", "search"
        lowered = text.lower()
        prefixes = [
            "i'm looking for", "im looking for", "i am looking for",
            "show me", "find", "search", "i want a", "i want an", "i want"
        ]
        for p in prefixes:
            if lowered.startswith(p):
                text = text[len(p):].strip(" :,-")
                break
        return text if text else None

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        query = self._extract_query(tracker) or "furniture"
        q = quote_plus(query)

        # Base URL to your customer search UI
        base = "http://localhost/FYP-25-S2-34-Chatbot/Src/Boundary/Customer/viewFurnitureUI.php"
        url = f"{base}?search={q}"

        # Friendly message + direct link
        dispatcher.utter_message(
            text=f"LuxFurn's options for '{query}' are: <a href='{url}' target='_blank'>Click here</a>"
        )
        return []
