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

# ✅ NEW
if "design_spec" not in st.session_state:
    st.session_state.design_spec = None

if "design_mode" not in st.session_state:
    st.session_state.design_mode = False

# -----------------------
# 🧱 Layout
# -----------------------
left, right = st.columns([3, 2], gap="large")

# -----------------------
# 💬 CHAT UI
# -----------------------
with left:
    st.subheader("💬 CAD Assistant")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Describe your model or changes...")

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
# 🧠 Intent Classifier
# -----------------------
def classify_intent(user_input):
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {
                "role": "system",
                "content": """
Classify user input into ONE of:

1. CAD_REQUEST
2. DESIGN DESCRIPTION
3. GENERAL_QUESTION
4. UNCLEAR
5. GREETINGS

Examples:
"Hi" → GREETINGS
"Who are you?" → GREETINGS
"create cube" → CAD_REQUEST
"design donut" → DESIGN DESCRIPTION
"what is donut shape?" → DESIGN DESCRIPTION
"What does a Steering wheel look like?" → DESIGN DESCRIPTION
"who is MS Dhoni>" → GENERAL_QUESTION
"asdf" → UNCLEAR

Return only the label.
"""
            },
            {"role": "user", "content": user_input}
        ]
    )
    return response.choices[0].message.content.strip()

# -----------------------
# 🧠 Explain / Refine Shape
# -----------------------
def explain_shape(prompt):
    
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {
                "role": "system",
                "content": """
You are a CAD assistant.

Explain or refine the object in geometric/CAD terms:
- shape
- structure
- parameters
- how it's modeled
- Short and breif less than 250 words
Continuously improve the design based on user input.
"""
            },
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

# -----------------------
# 🤖 MAIN FLOW
# -----------------------
MAX_RETRIES = 5

if st.session_state.pending_prompt:

    prompt = st.session_state.pending_prompt

    # -----------------------
    # ✏️ DESIGN REFINEMENT MODE (NEW CORE)
    # -----------------------
    if st.session_state.design_mode:

        if any(word in prompt.lower() for word in ["generate", "create", "build"]):
            prompt = st.session_state.design_spec
            st.session_state.design_mode = False

        else:
            with st.spinner(f"Thinking..."):
                updated_explanation = explain_shape(f"""
Current design:
{st.session_state.design_spec}

User modification:
{prompt}

Update the design accordingly.
""")

            st.session_state.design_spec = updated_explanation

            st.session_state.messages.append({
                "role": "assistant",
                "content": updated_explanation
            })

            st.session_state.pending_prompt = None
            st.rerun()

    else:
        intent = classify_intent(prompt)

        # -----------------------
        # 🚫 GENERAL
        # -----------------------
        if intent == "GENERAL_QUESTION" or intent == "GREETINGS":
            st.session_state.messages.append({
                "role": "assistant",
                "content": "🤖 I specialize in 3D CAD modeling. Describe the object you want to create."
            })
            st.session_state.pending_prompt = None
            st.rerun()

        # -----------------------
        # ❓ UNCLEAR
        # -----------------------
        elif intent == "UNCLEAR":
            st.session_state.messages.append({
                "role": "assistant",
                "content": "❓ Could you clarify what you want to design?"
            })
            st.session_state.pending_prompt = None
            st.rerun()

        # -----------------------
        # 🧠 DESIGN DESCRIPTION → START DESIGN MODE
        # -----------------------
        elif intent == "DESIGN DESCRIPTION":
            with st.spinner(f"Thinking..."):
                explanation = explain_shape(prompt)

            st.session_state.messages.append({
                "role": "assistant",
                "content": explanation
            })

            st.session_state.design_mode = True
            st.session_state.design_spec = explanation

            st.session_state.pending_prompt = None
            st.rerun()

    # -----------------------
    # 🔁 Correction Handling
    # -----------------------
    if any(word in prompt.lower() for word in ["wrong", "fix", "change"]):
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Got it 👍 What should I adjust?"
        })
        st.session_state.pending_prompt = None
        st.rerun()

    # -----------------------
    # ✅ CAD GENERATION
    # -----------------------
    code = None
    error_message = None

    for attempt in range(MAX_RETRIES):

        with st.spinner(f"Generating... iteration {attempt+1}"):

            messages = [
                {
                    "role": "system",
                    "content": """
You are a CadQuery expert.

Rules:
- Generate full working CadQuery code
- Always define 'result'
- No explanation in code

Mappings:
- donut → torus
- ring → torus
- pipe → hollow cylinder
"""
                }
            ]

            for m in st.session_state.messages:
                messages.append(m)

            if st.session_state.last_code:
                messages.append({
                    "role": "user",
                    "content": f"""
Modify this:

{st.session_state.last_code}

Request:
{prompt}
"""
                })

            if code and error_message:
                messages.append({
                    "role": "user",
                    "content": f"""
Fix this:

{code}

Error:
{error_message}
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
                    cq.exporters.export(result, "output.step")
                    cq.exporters.export(result, "output.stl")

                    st.session_state.last_code = code

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"🛠️ Model created for: **{prompt}**"
                    })

                    st.success("✅ Model generated")

                    with open("output.step", "rb") as f:
                        st.download_button("Download STEP", f, "model.step")

                    with open("output.stl", "rb") as f:
                        st.download_button("Download STL", f, "model.stl")

                    with viewer_placeholder.container():
                        stl_from_file("output.stl", height=420)

                    break

                else:
                    error_message = "No result"

            except Exception as e:
                error_message = str(e)

            if attempt == MAX_RETRIES - 1:
                st.error(error_message)

    st.session_state.pending_prompt = None

# -----------------------
# 🔄 Reset
# -----------------------
st.markdown("---")
if st.button("🔄 Reset Conversation"):
    st.session_state.messages = []
    st.session_state.last_code = None
    st.session_state.pending_prompt = None
    st.session_state.design_mode = False
    st.session_state.design_spec = None
    st.success("Reset complete")
    st.rerun()
