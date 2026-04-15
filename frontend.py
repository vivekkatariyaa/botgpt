import os
import streamlit as st
import requests

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000/api")


def show_connection_error() -> None:
    """Human-friendly copy when the API is unreachable (connection refused, etc.)."""
    st.error(
        "We couldn't reach the chat service just now. "
        "It may still be starting, or it might be turned off—please wait a few seconds and try again."
    )
    st.caption(
        "If you're running this project on your own machine, start the backend server from your project folder, "
        "then try logging in again. "
        f"This page is looking for the API at: {API_BASE}"
    )


# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BOTO GPT",
    page_icon="🤖",
    layout="wide",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0f1117; }
    .stChatMessage { border-radius: 12px; margin-bottom: 8px; }
    .sidebar-title { font-size: 22px; font-weight: 700; color: #ffffff; margin-bottom: 4px; }
    .sidebar-sub   { font-size: 12px; color: #888; margin-bottom: 20px; }
    .conv-btn { width: 100%; text-align: left; }
</style>
""", unsafe_allow_html=True)

# ─── Session state defaults ───────────────────────────────────────────────────
if "token"           not in st.session_state: st.session_state.token           = None
if "username"        not in st.session_state: st.session_state.username        = ""
if "conversations"   not in st.session_state: st.session_state.conversations   = []
if "active_conv_id"  not in st.session_state: st.session_state.active_conv_id  = None
if "messages"        not in st.session_state: st.session_state.messages        = []


def format_api_error(r: requests.Response) -> str:
    """Turn API JSON (e.g. DRF field errors) into short, readable text."""
    try:
        payload = r.json()
    except ValueError:
        text = (r.text or "").strip()
        return text[:500] if text else f"Request failed (HTTP {r.status_code}). Please try again."

    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return str(payload)

    if "detail" in payload:
        d = payload["detail"]
        if isinstance(d, list):
            return " ".join(str(x) for x in d)
        return str(d)

    field_labels = {
        "username": "Username",
        "email": "Email",
        "password": "Password",
        "non_field_errors": "",
    }
    parts: list[str] = []
    for field, messages in payload.items():
        if field == "detail":
            continue
        label = field_labels.get(field, field.replace("_", " ").capitalize())
        if isinstance(messages, list):
            msg = " ".join(str(m) for m in messages)
        else:
            msg = str(messages)
        if field == "non_field_errors":
            parts.append(msg)
        elif label:
            parts.append(f"{label}: {msg}")
        else:
            parts.append(msg)

    if parts:
        return "\n".join(parts)

    if "error" in payload:
        return str(payload["error"])

    return f"Something went wrong (HTTP {r.status_code}). Please try again."


# ─── API helpers ─────────────────────────────────────────────────────────────
def auth_headers():
    return {"Authorization": f"Token {st.session_state.token}"}


def api_register(username, email, password):
    r = requests.post(f"{API_BASE}/auth/register/",
                      json={"username": username, "email": email, "password": password})
    return r

def api_login(username, password):
    r = requests.post(f"{API_BASE}/auth/login/",
                      json={"username": username, "password": password})
    return r

def api_list_conversations():
    r = requests.get(f"{API_BASE}/conversations/", headers=auth_headers())
    if r.status_code == 200:
        return r.json().get("results", [])
    return []

def api_get_conversation(conv_id):
    r = requests.get(f"{API_BASE}/conversations/{conv_id}/", headers=auth_headers())
    if r.status_code == 200:
        return r.json()
    return None

def api_start_conversation(first_message, mode="open"):
    r = requests.post(f"{API_BASE}/conversations/",
                      headers=auth_headers(),
                      json={"first_message": first_message, "mode": mode})
    return r

def api_send_message(conv_id, content):
    r = requests.post(f"{API_BASE}/conversations/{conv_id}/messages/",
                      headers=auth_headers(),
                      json={"content": content})
    return r

def api_delete_conversation(conv_id):
    r = requests.delete(f"{API_BASE}/conversations/{conv_id}/", headers=auth_headers())
    return r.status_code == 204

def load_conversation(conv_id):
    conv = api_get_conversation(conv_id)
    if conv:
        st.session_state.active_conv_id = conv_id
        st.session_state.messages = [
            m for m in conv["messages"] if m["role"] in ("user", "assistant")
        ]

def refresh_conversations():
    st.session_state.conversations = api_list_conversations()


# ─── AUTH SCREEN ─────────────────────────────────────────────────────────────
if not st.session_state.token:
    st.markdown("<h1 style='text-align:center;'>🤖 BOTO GPT</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#888;'>Conversational AI — Open Chat & RAG Mode</p>", unsafe_allow_html=True)
    st.divider()

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        st.subheader("Login")
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login", use_container_width=True, type="primary"):
            if username and password:
                try:
                    r = api_login(username, password)
                except requests.exceptions.ConnectionError:
                    show_connection_error()
                else:
                    if r.status_code == 200:
                        data = r.json()
                        st.session_state.token    = data["token"]
                        st.session_state.username = data["user"]["username"]
                        refresh_conversations()
                        st.rerun()
                    else:
                        st.error(format_api_error(r) if r.content else "Invalid credentials. Please try again.")
            else:
                st.warning("Please enter username and password.")

    with tab_register:
        st.subheader("Create Account")
        reg_username = st.text_input("Username", key="reg_user")
        reg_email    = st.text_input("Email",    key="reg_email")
        reg_password = st.text_input("Password (min 8 chars)", type="password", key="reg_pass")
        if st.button("Register", use_container_width=True, type="primary"):
            if reg_username and reg_password:
                try:
                    r = api_register(reg_username, reg_email, reg_password)
                except requests.exceptions.ConnectionError:
                    show_connection_error()
                else:
                    if r.status_code == 201:
                        data = r.json()
                        st.session_state.token    = data["token"]
                        st.session_state.username = data["user"]["username"]
                        refresh_conversations()
                        st.success("Account created!")
                        st.rerun()
                    else:
                        st.error(format_api_error(r))
            else:
                st.warning("Please fill in all fields.")

    st.stop()


# ─── MAIN APP (logged in) ─────────────────────────────────────────────────────

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div class='sidebar-title'>🤖 BOTO GPT</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sidebar-sub'>Logged in as <b>{st.session_state.username}</b></div>", unsafe_allow_html=True)

    # New chat button
    if st.button("➕  New Conversation", use_container_width=True, type="primary"):
        st.session_state.active_conv_id = None
        st.session_state.messages       = []
        st.rerun()

    st.divider()
    st.markdown("**Recent Conversations**")

    # Conversation list
    refresh_conversations()
    for conv in st.session_state.conversations:
        title = conv.get("title") or "Untitled"
        mode_icon = "📄" if conv["mode"] == "rag" else "💬"
        col1, col2 = st.columns([5, 1])
        with col1:
            if st.button(f"{mode_icon} {title[:30]}", key=f"conv_{conv['id']}", use_container_width=True):
                load_conversation(conv["id"])
                st.rerun()
        with col2:
            if st.button("🗑", key=f"del_{conv['id']}"):
                if api_delete_conversation(conv["id"]):
                    if st.session_state.active_conv_id == conv["id"]:
                        st.session_state.active_conv_id = None
                        st.session_state.messages       = []
                    st.rerun()

    # PDF Upload — only shown when inside a RAG conversation
    if st.session_state.active_conv_id:
        conv = api_get_conversation(st.session_state.active_conv_id)
        if conv and conv["mode"] == "rag":
            st.divider()
            ready_docs = [d for d in conv.get("documents", []) if d["status"] == "ready"]
            doc_count  = len(ready_docs)
            MAX_DOCS   = 3

            st.markdown(f"**📄 Documents ({doc_count}/{MAX_DOCS})**")

            # Show existing documents
            for doc in ready_docs:
                st.markdown(f"- ✅ `{doc['filename']}` ({doc['chunk_count']} chunks)")

            if doc_count < MAX_DOCS:
                st.caption("Max file size: 50 MB • PDF only")
                uploaded_file = st.file_uploader(
                    "Upload a PDF",
                    type=["pdf"],
                    key="pdf_uploader",
                    label_visibility="collapsed",
                )
                if uploaded_file:
                    size_mb = uploaded_file.size / (1024 * 1024)
                    st.caption(f"File size: {size_mb:.1f} MB")
                    if st.button("Upload & Index PDF", use_container_width=True, type="primary"):
                        with st.spinner("Processing PDF... this may take a moment."):
                            r = requests.post(
                                f"{API_BASE}/conversations/{st.session_state.active_conv_id}/documents/",
                                headers=auth_headers(),
                                files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")},
                            )
                        if r.status_code == 201:
                            doc = r.json()
                            st.success(f"✅ Indexed {doc['chunk_count']} chunks from `{doc['filename']}`")
                            st.rerun()
                        else:
                            st.error(f"Upload failed: {format_api_error(r)}")
            else:
                st.warning(f"Maximum {MAX_DOCS} documents reached. Delete a conversation to upload more.")

    st.divider()
    if st.button("🚪 Logout", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ── Main chat area ────────────────────────────────────────────────────────────
if not st.session_state.active_conv_id:
    # Welcome screen
    st.markdown("<h2 style='text-align:center; margin-top:80px;'>What can I help you with?</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#888;'>Start a new conversation below</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("💬 **Open Chat**\nChat with AI on any topic")
    with col2:
        st.info("📄 **RAG Mode**\nUpload a PDF and chat with it")
    with col3:
        st.info("🔒 **Secure**\nYour conversations are private")

else:
    # Show conversation title + mode badge
    conv_data = api_get_conversation(st.session_state.active_conv_id)
    if conv_data:
        mode_label = "📄 RAG Mode" if conv_data["mode"] == "rag" else "💬 Open Chat"
        st.markdown(f"### {conv_data['title'] or 'Conversation'} &nbsp; `{mode_label}`", unsafe_allow_html=True)
        st.markdown(f"<small style='color:#888;'>Tokens used: {conv_data['total_tokens_used']}</small>", unsafe_allow_html=True)
        st.divider()

    # Render chat messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])


# ── Chat input (always visible at bottom) ─────────────────────────────────────
mode_choice = "open"
if not st.session_state.active_conv_id:
    mode_choice = st.radio(
        "Chat mode:",
        options=["open", "rag"],
        format_func=lambda x: "💬 Open Chat" if x == "open" else "📄 RAG Mode (chat with a PDF)",
        horizontal=True,
    )
    if mode_choice == "rag":
        st.info("📄 You can upload a PDF after the conversation starts. Select RAG mode, send your first message, then upload the PDF from the sidebar.")

MAX_MESSAGE_CHARS = 4000

user_input = st.chat_input("Type your message here… (max 4000 characters)")

if user_input:
    if len(user_input) > MAX_MESSAGE_CHARS:
        st.warning(f"Message too long ({len(user_input)}/{MAX_MESSAGE_CHARS} characters). Please shorten it.")
        st.stop()

    if not st.session_state.active_conv_id:
        # Start new conversation
        with st.spinner("Starting conversation..."):
            r = api_start_conversation(user_input, mode=mode_choice)
        if r.status_code == 201:
            conv = r.json()
            st.session_state.active_conv_id = conv["id"]
            st.session_state.messages = [
                m for m in conv["messages"] if m["role"] in ("user", "assistant")
            ]
            st.rerun()
        else:
            st.error(format_api_error(r))
    else:
        # Continue existing conversation
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Thinking..."):
                r = api_send_message(st.session_state.active_conv_id, user_input)
            if r.status_code == 200:
                reply = r.json()["content"]
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            else:
                st.error("LLM error. Please try again.")
