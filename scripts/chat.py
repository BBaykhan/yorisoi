"""Talk to the agent in the terminal (local mode). Type 'quit' to exit.

Usage:  python scripts/chat.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from yorisoi_agent import handle_request  # noqa: E402

print("よりそい (local). 'quit' で終了します。")
while True:
    try:
        text = input("\nあなた > ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if text.lower() in {"quit", "exit"}:
        break
    if text:
        print("よりそい >", handle_request({"prompt": text}, "terminal")["reply"])
