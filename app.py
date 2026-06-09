import streamlit as st
from openai import OpenAI
import cadquery as cq
from streamlit_stl import stl_from_file
import json

# -----------------------
# 🔐 Setup
# -----------------------
client = OpenAI()

st.set_page_config(page_title="IntelliCAD AI", layout="wide", page_icon="icon.png")
st.title("🧠 IntelliCAD AI")

# -----------------------
# 🧠 Session State
# -----------------------
for key, default in {
    "messages": [],
    "last_code": None,
    "pending_prompt": None,
    "model_ready": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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

    user_input = st.chat_input("Describe your model or ask anything...")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.pending_prompt = user_input
        st.rerun()

# -----------------------
# 🔍 CAD VIEW
# -----------------------
with right:
    with st.container(border=True):
        st.subheader("🔍 CAD View")
        viewer_placeholder = st.empty()
        if st.session_state.model_ready:
            with viewer_placeholder.container():
                stl_from_file("output.stl", height=420)
        else:
            viewer_placeholder.image("icon.png", use_container_width=True)

# -----------------------
# 🔧 Tool Definition
# Only run_cadquery is a custom tool.
# Web search is handled natively by OpenAI — no code needed.
# -----------------------
TOOLS = [
    {
        "type": "web_search_preview",     # ← OpenAI built-in, free to use, no extra key
    },
    {
        "type": "function",
        "name": "run_cadquery",
        "description": (
            "Execute CadQuery Python code to generate a 3D model. "
            "The code MUST define a variable named 'result' holding the final CadQuery shape. "
            "Returns 'SUCCESS' or an 'ERROR: <message>' string. "
            "If you get an error, fix the code and call this again."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Complete, runnable CadQuery Python code. Must define 'result'."
                }
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]

# -----------------------
# ⚙️ run_cadquery tool
# -----------------------
def run_cadquery(code: str) -> str:
    try:
        local_vars = {}
        exec(code, {"cq": cq}, local_vars)
        result = local_vars.get("result")
        if result is None:
            return "ERROR: Code ran but 'result' was not defined. Assign your final shape to 'result'."
        cq.exporters.export(result, "output.step")
        cq.exporters.export(result, "output.stl")
        st.session_state.last_code = code
        st.session_state.model_ready = True
        return "SUCCESS: 3D model generated and saved as output.stl and output.step."
    except Exception as e:
        return f"ERROR: {e}"

# -----------------------
# 🧠 System Prompt
# -----------------------
SYSTEM_PROMPT = """You are IntelliCAD — an expert agentic AI for generating precise 3D CAD models using CadQuery.

## Your tools
1. web_search        — built-in web search. Use it to find real-world dimensions, standards,
                       and CadQuery API syntax before writing code.
2. run_cadquery       — executes CadQuery Python code and generates the 3D model.

## Your workflow
1. For any real-world object (bolt, nut, gear, wheel, pipe, bracket, etc.)
   → web_search for its standard dimensions FIRST (e.g. "M8 hex bolt ISO 4014 dimensions mm").
2. If you are unsure about CadQuery syntax for a shape
   → web_search "cadquery <shape> example" before writing code.
3. Write clean CadQuery code and call run_cadquery.
4. If it returns ERROR → read it, fix the code, call run_cadquery again (max 4 attempts).
5. Once SUCCESS → give the user a short summary: what was built and the key dimensions used.

## CadQuery rules
- Always define 'result' as the final shape.
- Use metric units (mm) unless the user specifies otherwise.
- Import nothing — only 'cq' is available in the execution scope.

## CadQuery name mappings
donut/ring → torus | pipe/tube → hollow cylinder

## Off-topic requests
Politely say you specialize in 3D CAD modeling only."""

# -----------------------
# 🤖 Agent Loop
# Uses the Responses API — web search is automatic, no Tavily needed.
# -----------------------
MAX_STEPS = 14


def run_agent(user_message: str, trace_box) -> tuple[str, bool]:
    """
    Runs the agentic loop using the OpenAI Responses API.
    - web_search_call items are handled internally by OpenAI (no tool output needed).
    - function_call items (run_cadquery) are handled by us.
    Returns (final_text, model_was_generated).
    """

    # Build the input list: system + recent history + new user message
    input_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in st.session_state.messages[-8:]:
        input_messages.append(m)
    input_messages.append({"role": "user", "content": user_message})

    model_generated = False
    steps = 0

    while steps < MAX_STEPS:
        response = client.responses.create(
            model="gpt-4o",
            tools=TOOLS,
            input=input_messages,
        )

        steps += 1

        # ── Show agent activity in the UI trace ──
        for item in response.output:
            if item.type == "web_search_call":
                # Web search was triggered — show it (OpenAI handles the actual search)
                with trace_box:
                    action = getattr(item, "action", None)
                    if action and hasattr(action, "query"):
                        queries = action.query if isinstance(action.query, list) else [action.query]
                        for q in queries:
                            st.info(f"🔍 **Web search:** _{q}_")
                    else:
                        st.info("🔍 **Searching the web...**")

        # ── Check if there are custom function calls to handle ──
        function_calls = [item for item in response.output if item.type == "function_call"]

        if not function_calls:
            # No more tool calls — extract the final text from the message item
            for item in response.output:
                if item.type == "message":
                    text = "".join(
                        part.text for part in item.content if hasattr(part, "text")
                    )
                    return text, model_generated
            return "Done.", model_generated

        # ── Extend input with everything the model output this turn ──
        input_messages.extend(response.output)

        # ── Execute each function call and feed results back ──
        for fc in function_calls:
            args = json.loads(fc.arguments)

            with trace_box:
                st.info("⚙️ **Running CadQuery code...**")

            result = run_cadquery(args["code"])

            if result.startswith("SUCCESS"):
                model_generated = True
                with trace_box:
                    st.success("✅ Model generated!")
            else:
                with trace_box:
                    st.warning(f"⚠️ {result[:150]}")

            # Feed result back to the model
            input_messages.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": result,
            })

    return "⚠️ Reached the maximum number of steps. Please try a simpler or more specific request.", model_generated


# -----------------------
# 🚀 Main execution
# -----------------------
if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt

    with left:
        with st.chat_message("assistant"):
            trace_box = st.container()
            with st.spinner("Agent working…"):
                final_response, model_generated = run_agent(prompt, trace_box)

            st.markdown(final_response)

            if model_generated:
                col1, col2 = st.columns(2)
                with col1:
                    with open("output.step", "rb") as f:
                        st.download_button("⬇️ Download STEP", f, "model.step")
                with col2:
                    with open("output.stl", "rb") as f:
                        st.download_button("⬇️ Download STL", f, "model.stl")

    if model_generated:
        with viewer_placeholder.container():
            stl_from_file("output.stl", height=420)

    st.session_state.messages.append({"role": "assistant", "content": final_response})
    st.session_state.pending_prompt = None
    st.rerun()

# -----------------------
# 🔄 Reset
# -----------------------
st.markdown("---")
if st.button("🔄 Reset Conversation"):
    st.session_state.messages = []
    st.session_state.last_code = None
    st.session_state.pending_prompt = None
    st.session_state.model_ready = False
    st.success("Reset complete")
    st.rerun()
