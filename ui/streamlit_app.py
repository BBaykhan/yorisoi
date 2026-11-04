"""Yorisoi UI: big text, voice replies, photo reading, and reminders that ring.

Run:  streamlit run ui/streamlit_app.py
"""
import io
import sys
import uuid
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import config  # noqa: E402
import store  # noqa: E402
from agent_client import ask  # noqa: E402
from voice import speak  # noqa: E402

st.set_page_config(page_title="よりそい", page_icon="🌸", layout="centered")
st.markdown(
    """
    <style>
      html, body, [data-testid="stMarkdownContainer"] p { font-size: 22px; line-height: 1.7; }
      div.stButton > button { font-size: 24px; padding: 0.5em 1.2em; border-radius: 14px; }
      [data-testid="stChatInput"] textarea { font-size: 22px; }
    </style>
    """,
    unsafe_allow_html=True,
)

ss = st.session_state
ss.setdefault("session_id", str(uuid.uuid4()))
ss.setdefault("messages", [])      # list of {"role", "text"}
ss.setdefault("rung", set())       # reminder ids already announced by voice
ss.setdefault("upload_key", 0)
ss.setdefault("last_audio", None)


def fmt_time(iso: str) -> str:
    t = store.parse_time(iso)
    return f"{t.month}月{t.day}日 {t:%H:%M}"


def prepare_image(file) -> bytes:
    """Fix rotation, shrink to max 1600px, save as JPEG (keeps Bedrock under its image size limit)."""
    img = ImageOps.exif_transpose(Image.open(file)).convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


# ---------- sidebar ----------
with st.sidebar:
    st.header("設定 / Settings")
    st.write(f"利用者: {config.USER_NAME}")
    st.write("Agent: " + ("AgentCore Runtime" if config.AGENT_RUNTIME_ARN else "local"))
    st.write("Family alert: " + ("ON" if config.SNS_TOPIC_ARN else "not configured"))
    st.write(f"Alert after: {config.ESCALATION_MINUTES} min")
    if st.button("新しい会話"):
        ss.session_id, ss.messages = str(uuid.uuid4()), []
        st.rerun()

st.title("🌸 よりそい")
st.caption("お薬・予定のリマインダーと、写真の読み上げ")


# ---------- reminders that are due (checked every 15 seconds) ----------
@st.fragment(run_every="15s")
def due_panel():
    for r in store.due_reminders():
        rid = r["reminder_id"]
        with st.container(border=True):
            st.markdown(f"## ⏰ {r['title']}")
            st.write(f"{fmt_time(r['due_at'])}　{r.get('note', '')}")
            label = "✅ 飲みました" if r["kind"] == "medicine" else "✅ わかりました"
            if st.button(label, key=f"done-{rid}", use_container_width=True):
                store.complete(rid)
                st.rerun()
        if rid not in ss.rung:
            ss.rung.add(rid)
            audio = speak(f"{config.USER_NAME}、{r['title']}の時間です。")
            if audio:
                st.audio(audio, format="audio/mp3", autoplay=True)


due_panel()

# ---------- conversation ----------
for m in ss.messages:
    with st.chat_message(m["role"], avatar="🧓" if m["role"] == "user" else "🌸"):
        st.write(m["text"])

if ss.last_audio:
    st.audio(ss.last_audio, format="audio/mp3", autoplay=True)
    ss.last_audio = None

with st.expander("📷 写真を読む（お薬の袋・手紙など）"):
    photo = st.file_uploader("写真をえらぶ", type=["jpg", "jpeg", "png"], key=f"up-{ss.upload_key}")
    read_photo = st.button("この写真を読んで", disabled=photo is None, use_container_width=True)

prompt = st.chat_input("ここに書いてください（例：明日の10時に病院）")

if prompt or read_photo:
    image_bytes = prepare_image(photo) if photo else None
    shown = prompt or "（写真を読んでください）"
    ss.messages.append({"role": "user", "text": shown + (" 📷" if image_bytes else "")})
    with st.spinner("考え中です…"):
        try:
            reply = ask(prompt or "", ss.session_id, image_bytes=image_bytes)
        except Exception as e:  # show errors instead of a blank screen
            reply = f"ごめんなさい、エラーが起きました。({type(e).__name__}: {e})"
    ss.messages.append({"role": "assistant", "text": reply})
    ss.last_audio = speak(reply)
    ss.upload_key += 1  # clear the photo so it is not sent again
    st.rerun()

# ---------- upcoming reminders ----------
st.divider()
st.subheader("これからの予定")
upcoming = store.list_reminders()
if not upcoming:
    st.write("まだありません。")
for r in upcoming:
    icon = "💊" if r["kind"] == "medicine" else ("🏥" if r["kind"] == "appointment" else "📌")
    st.write(f"{icon} {fmt_time(r['due_at'])}　{r['title']}")
