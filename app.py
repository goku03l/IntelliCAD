import streamlit as st
from openai import OpenAI
import cadquery as cq
from streamlit_stl import stl_from_file

# 🔐 Use Streamlit secrets (IMPORTANT)
# Put this in .streamlit/secrets.toml:


# 🔐 Use Streamlit secrets
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="IntelliCAD AI", layout="wide")

st.title("🧠 IntelliCAD AI")

# -----------------------
# 🧠 Session State
# -----------------------
if "history" not in st.session_state:
    st.session_state.history = []

if "last_code" not in st.session_state:
    st.session_state.last_code = None

if "error" not in st.session_state:
    st.session_state.error = None


# -----------------------
# 🧱 MAIN LAYOUT (FIXED GRID)
# -----------------------
main_left, main_right = st.columns([3, 2], gap="large")


# -----------------------
# LEFT SIDE (CONTROLS)
# -----------------------
with main_left:

    st.subheader("⚙️ Controls")

    mode = st.radio("Mode", ["New Design", "Iterate"], horizontal=True)

    if st.button("🔄 Reset"):
        st.session_state.history = []
        st.session_state.last_code = None
        st.session_state.error = None
        st.success("Reset complete")

    prompt = st.text_area(
        "Describe your model or changes:",
        height=150,
        placeholder="e.g., Create a box 20x20x10\nor\nAdd 4 holes on top"
    )

    generate_btn = st.button("🚀 Generate / Update Model")

    st.markdown("---")

    # 📜 History
    with st.expander("🕘 Iteration History"):
        if st.session_state.history:
            for i, h in enumerate(st.session_state.history):
                st.write(f"{i+1}. {h}")
        else:
            st.write("No history yet.")


# -----------------------
# RIGHT SIDE (CAD VIEW)
# -----------------------
with main_right:
    with st.container(border=True):
        st.subheader("🔍 CAD View")
        viewer_placeholder = st.empty()


# -----------------------
# 🧹 Clean Code Helper
# -----------------------
def clean_code(code_text):
    if "```" in code_text:
        code_text = code_text.split("```")[1]
        code_text = code_text.replace("python", "")
    return code_text.strip()


# -----------------------
# 🤖 GENERATE LOGIC
# -----------------------
MAX_RETRIES = 5

if generate_btn:

    code = None
    error_message = None

    for attempt in range(MAX_RETRIES):

        with st.spinner(f"Iteration {attempt + 1}..."):

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

            # Iterate mode
            if mode == "Iterate" and st.session_state.last_code:
                messages.append({
                    "role": "user",
                    "content": f"""
Modify this existing CadQuery model:

{st.session_state.last_code}

User request:
{prompt}

Return FULL updated code only.
"""
                })

            # Fix errors
            elif code and error_message:
                messages.append({
                    "role": "user",
                    "content": f"""
Fix this CadQuery code:

{code}

Error:
{error_message}

Return ONLY corrected full code.
"""
                })

            # New design
            else:
                messages.append({
                    "role": "user",
                    "content": prompt
                })

            # API call
            response = client.chat.completions.create(
                model="gpt-5.4",
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

                    # Save state
                    st.session_state.last_code = code
                    st.session_state.error = None
                    st.session_state.history.append(prompt)

                    st.success("✅ Model generated successfully!")

                    # Downloads
                    d1, d2 = st.columns(2)

                    with d1:
                        with open("output.step", "rb") as f:
                            st.download_button("Download STEP", f, "model.step")

                    with d2:
                        with open("output.stl", "rb") as f:
                            st.download_button("Download STL", f, "model.stl")

                    # Update CAD Viewer (RIGHT PANEL)
                    with viewer_placeholder.container():
                        stl_from_file("output.stl", height=420)

                    break

                else:
                    error_message = "No 'result' object returned."

            except Exception as e:
                error_message = str(e)
                st.session_state.error = error_message

            if attempt == MAX_RETRIES - 1:
                st.error("❌ Failed after multiple attempts.")
                st.text(error_message)
