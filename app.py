import streamlit as st
from openai import OpenAI
import cadquery as cq
from streamlit_stl import stl_from_file

# -----------------------
# 🔐 Setup
# -----------------------
client = OpenAI()

st.set_page_config(page_title="IntelliCAD AI", layout="wide", page_icon="icon.png")
st.title("🧠 IntelliCAD AI")

# -----------------------
# 🧠 Session State
# -----------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_code" not in st.session_state:
    st.session_state.last_code = None

if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

# -----------------------
# 🧱 Layout
# -----------------------
left, right = st.columns([3, 2], gap="large")

# -----------------------
# 💬 CHAT UI
# -----------------------
with left:
    st.subheader("💬 CAD Assistant")

    # Show messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    user_input = st.chat_input("Describe your model or changes...")

    # Handle input (STEP 1: show immediately)
    if user_input:
        st.session_state.messages.append({
            "role": "user",
            "content": user_input
        })

        st.session_state.pending_prompt = user_input
        st.rerun()

# -----------------------
# 🔍 CAD VIEW
# -----------------------
with right:
    with st.container(border=True):
        st.subheader("🔍 CAD View")
        viewer_placeholder = st.empty()
        viewer_placeholder.image("icon.png", use_container_width=True)

# -----------------------
# 🧹 Clean Code
# -----------------------
def clean_code(code_text):
    if "```" in code_text:
        code_text = code_text.split("```")[1]
        code_text = code_text.replace("python", "")
    return code_text.strip()

# -----------------------
# 🤖 GENERATION (STEP 2)
# -----------------------
MAX_RETRIES = 5

if st.session_state.pending_prompt:

    prompt = st.session_state.pending_prompt

    code = None
    error_message = None

    for attempt in range(MAX_RETRIES):

        with st.spinner("Thinking..."):

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a CadQuery expert.\n"
                        "Generate ONLY valid CadQuery Python code.\n"
                        "Always return FULL code.\n"
                        "Ensure variable 'result' exists.\n"
                        "Do not include explanations."
                    )
                }
            ]

            # Add conversation (text only)
            for m in st.session_state.messages:
                messages.append({
                    "role": m["role"],
                    "content": m["content"]
                })

            # Include last code for iteration
            if st.session_state.last_code:
                messages.append({
                    "role": "user",
                    "content": f"""
Modify this existing model:

{st.session_state.last_code}

User request:
{prompt}

Return full updated code only.
"""
                })

            # Error fixing
            if code and error_message:
                messages.append({
                    "role": "user",
                    "content": f"""
Fix this code:

{code}

Error:
{error_message}

Return corrected full code only.
"""
                })

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=messages,
            )

            code = clean_code(response.choices[0].message.content)

            try:
                local_vars = {}
                exec(code, {"cq": cq}, local_vars)

                result = local_vars.get("result")

                if result:
                    # Export files
                    cq.exporters.export(result, "output.step")
                    cq.exporters.export(result, "output.stl")

                    st.session_state.last_code = code

                    # Assistant response (clean, no code)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"🛠️ Done: {prompt}"
                    })

                    st.success("✅ Model updated")

                    # Downloads
                    d1, d2 = st.columns(2)

                    with d1:
                        with open("output.step", "rb") as f:
                            st.download_button("Download STEP", f, "model.step")

                    with d2:
                        with open("output.stl", "rb") as f:
                            st.download_button("Download STL", f, "model.stl")

                    # Render viewer
                    with viewer_placeholder.container():
                        stl_from_file("output.stl", height=420)

                    break

                else:
                    error_message = "No result returned"

            except Exception as e:
                error_message = str(e)

            if attempt == MAX_RETRIES - 1:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "❌ Failed to generate model"
                })
                st.error(error_message)

    # ✅ IMPORTANT: clear pending prompt
    st.session_state.pending_prompt = None

# -----------------------
# 🔄 Reset
# -----------------------
st.markdown("---")
if st.button("🔄 Reset Conversation"):
    st.session_state.messages = []
    st.session_state.last_code = None
    st.session_state.pending_prompt = None
    st.success("Reset complete")
    st.rerun()
