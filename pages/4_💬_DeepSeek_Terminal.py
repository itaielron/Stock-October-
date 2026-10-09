import streamlit as st
import os
import openai
import sqlite3
import uuid
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="DeepSeek Terminal", layout="wide")

st.markdown("""
<style>
    footer {visibility: hidden;}
    h1, h2, h3 { color: #4da6ff !important; font-weight: 600; letter-spacing: 0.5px; }
    .chat-message { padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; display: flex }
    .chat-message.user { background-color: #2b313e }
    .chat-message.bot { background-color: #1a202c }
</style>
""", unsafe_allow_html=True)

# DB Helper
def get_db():
    return sqlite3.connect("hub.db", check_same_thread=False)

def load_sessions():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT session_id, MIN(timestamp) FROM deepseek_chats GROUP BY session_id ORDER BY MIN(timestamp) DESC")
    sessions = c.fetchall()
    conn.close()
    return [s[0] for s in sessions]

def load_messages(session_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role, content FROM deepseek_chats WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
    msgs = [{"role": row[0], "content": row[1]} for row in c.fetchall()]
    conn.close()
    return msgs

def save_message(session_id, role, content):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO deepseek_chats (session_id, role, content) VALUES (?, ?, ?)", (session_id, role, content))
    conn.commit()
    conn.close()

# Session State Init
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for History
with st.sidebar:
    st.markdown("### Chat History")
    if st.button("➕ New Uplink"):
        st.session_state.current_session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    
    st.markdown("---")
    past_sessions = load_sessions()
    for sid in past_sessions:
        # Get first message to use as title
        first_msg = load_messages(sid)
        title = first_msg[0]['content'][:25] + "..." if first_msg else "Empty Session"
        
        # Highlight active session
        btn_type = "primary" if sid == st.session_state.current_session_id else "secondary"
        if st.button(title, key=sid, type=btn_type):
            st.session_state.current_session_id = sid
            st.session_state.messages = load_messages(sid)
            st.rerun()

st.title("💬 DeepSeek Direct Terminal")
st.markdown("---")
st.markdown("Direct uplink to the central DeepSeek intelligence engine managing your background tasks.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Enter command or query for DeepSeek..."):
    # Add User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message(st.session_state.current_session_id, "user", prompt)
    
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        try:
            client = openai.OpenAI(
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com"
            )
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
            )
            full_response = response.choices[0].message.content
            message_placeholder.markdown(full_response)
            
            # Add Assistant Message
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            save_message(st.session_state.current_session_id, "assistant", full_response)
            
            # Refresh to update sidebar title if this is the first message
            if len(st.session_state.messages) == 2:
                st.rerun()
                
        except Exception as e:
            message_placeholder.error(f"Uplink Error: {str(e)}")
