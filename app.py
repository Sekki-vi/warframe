#!/usr/bin/env python3
"""Flask app for the Warframe Market RAG chatbot."""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request, session

from chat.config import get_chat_config
from chat.service import chat

app = Flask(__name__)
_cfg = get_chat_config()
app.secret_key = _cfg["flask_secret_key"]


def _get_history() -> list[dict[str, str]]:
    return session.get("history", [])


def _set_history(history: list[dict[str, str]]) -> None:
    session["history"] = history


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
        result = chat(message, _get_history())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    _set_history(result["history"])
    return jsonify(
        {
            "reply": result["reply"],
            "sources": result["sources"],
        }
    )


@app.route("/api/clear", methods=["POST"])
def api_clear():
    session.pop("history", None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=_cfg["flask_port"], debug=True)
