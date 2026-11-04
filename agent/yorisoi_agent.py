"""Builds the Yorisoi agent and handles one request (text and/or photo)."""
import base64

from strands import Agent
from strands.models import BedrockModel

import config
import store
from hooks import SafetyLimits
from tools import ALL_TOOLS

SYSTEM_PROMPT = f"""あなたは「よりそい」です。日本で一人暮らしをする高齢者（{config.USER_NAME}）の毎日を支える、やさしいアシスタントです。

話し方:
- やさしい日本語で、短い文で話します。1回の返事は4文くらいまで。
- 表や記号（*、#、|）は使いません。返事は音声で読み上げられます。
- 日時は「11月3日（火）の朝8時」のように言います。

できること:
- 予定やお薬の時間を覚えて、時間になったら知らせる（add_reminders）。
- 写真（お薬の袋、病院や役所からの手紙など）を読んで、大事なことをわかりやすく説明する。
- お薬の袋に飲む時間が書いてあれば、確認してからリマインダーを登録する。
- 「飲みました」と言われたら confirm_done で記録する。
- 頼まれたとき、または体調が悪そうなときは notify_family で家族に知らせる。

安全のためのルール（必ず守る）:
- 病気の診断はしません。お薬の量や飲み方を変えるアドバイス、飲み合わせの判断はしません。
  そういう質問には、書いてあることだけを伝え、「薬剤師さんかお医者さんに確認しましょう」と言います。
- 飲み忘れても、2回分をまとめて飲むようにすすめません。
- 胸の痛み、息苦しさ、意識がおかしい、ひどいけがなど、命にかかわりそうなときは、
  すぐに119番に電話するように伝え、notify_family で家族にも知らせます。
- 写真が読みにくいときは、推測せず、もう一度撮ってもらいます。
- 飲み忘れ・飲む量・飲む時間の質問には、次のことだけを伝えます。
  (1) 2回分をまとめて飲まないこと (2) 薬袋に書いてあること (3) どうするかはお薬によって違うので、薬局か病院に電話して聞くこと。
  「とばす」「飲まずに」「すぐ飲む」「次の時間から飲む」など、いつ・どう飲むかの指示は絶対に言いません。
  答えの例：「2回分をまとめて飲むのはやめておきましょう。薬袋にも、2回分を一度に飲まないように書いてあります。今回どうするかはお薬によって違うので、薬局に電話して聞いてみましょう。」

ユーザーのメッセージの最初に現在の日時が書いてあります。「明日」「3時間後」などはそれをもとに計算します。
"""

WEEKDAYS = "月火水木金土日"
_agents: dict[str, Agent] = {}


def _get_agent(session_id: str) -> Agent:
    """One Agent per session so the conversation is remembered."""
    if session_id not in _agents:
        model = BedrockModel(model_id=config.MODEL_ID, region_name=config.AWS_REGION) if config.MODEL_ID \
            else BedrockModel(region_name=config.AWS_REGION)
        _agents[session_id] = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            hooks=[SafetyLimits()],
            callback_handler=None,  # no printing; we return the final text
        )
    return _agents[session_id]


def handle_request(payload: dict, session_id: str = "local") -> dict:
    """payload: {"prompt": str, "image_b64": str (optional), "image_format": "jpeg"|"png"}"""
    text = (payload.get("prompt") or "").strip()
    image_b64 = payload.get("image_b64")
    if not text and not image_b64:
        return {"reply": "どうしましたか？"}
    if not text:
        text = "この写真を読んで、大事なことをわかりやすく教えてください。"

    t = store.now()
    header = f"[現在の日時: {t:%Y-%m-%d %H:%M}（{WEEKDAYS[t.weekday()]}）日本時間]\n"
    content = [{"text": header + text}]
    if image_b64:
        fmt = (payload.get("image_format") or "jpeg").lower().replace("jpg", "jpeg")
        content.append({"image": {"format": fmt, "source": {"bytes": base64.b64decode(image_b64)}}})

    result = _get_agent(session_id)(content)
    return {"reply": str(result).strip()}
