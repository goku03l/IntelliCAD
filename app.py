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
st.title("🧠 IntelliCAD AI — Agentic")

# -----------------------
# 🧠 Session State
# -----------------------
for key, default in {
    "messages": [],
    "last_code": None,
    "pending_prompt": None,
    "model_ready": False,
    "design_plan": None,
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
# 🔍 CAD VIEW + DESIGN PLAN
# -----------------------
with right:
    # Design plan card (shows agent's reasoning before generation)
    if st.session_state.design_plan:
        with st.container(border=True):
            st.caption("🗂 Design plan")
            plan = st.session_state.design_plan
            st.markdown(f"**{plan.get('object', '')}**")
            if plan.get("dimensions"):
                st.markdown("📐 **Dimensions**")
                st.markdown(plan["dimensions"])
            if plan.get("operations"):
                st.markdown("⚙️ **Operations**")
                for op in plan["operations"]:
                    st.markdown(f"- {op}")
            if plan.get("notes"):
                st.caption(plan["notes"])

    with st.container(border=True):
        st.subheader("🔍 CAD View")
        viewer_placeholder = st.empty()
        if st.session_state.model_ready:
            with viewer_placeholder.container():
                stl_from_file("output.stl", height=380)
        else:
            viewer_placeholder.image("icon.png", use_container_width=True)

# -----------------------
# 🔧 Tools
# -----------------------
TOOLS = [
    {
        "type": "web_search_preview",
    },
    {
        "type": "function",
        "name": "plan_design",
        "description": (
            "Before writing any CadQuery code, call this to lock down the design. "
            "Specify the exact object, all dimensions, and the ordered list of CadQuery "
            "operations you will use. This ensures the generated model matches user intent. "
            "ALWAYS call this before run_cadquery."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "object": {
                    "type": "string",
                    "description": "What is being modelled, e.g. 'M8 hex bolt ISO 4014'"
                },
                "dimensions": {
                    "type": "string",
                    "description": "All key dimensions as a readable string, e.g. 'length: 80mm, head_diameter: 13mm, thread_pitch: 1.25mm'"
                },
                "operations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered CadQuery operations, e.g. ['box 13x13x5 for head', 'extrude cylinder for shank', 'fillet edges']"
                },
                "notes": {
                    "type": "string",
                    "description": "Any special considerations, tolerances, or assumptions. Use empty string if none."
                }
            },
            "required": ["object", "dimensions", "operations", "notes"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "run_cadquery",
        "description": (
            "Execute CadQuery Python code to generate the 3D model. "
            "Must define a variable 'result' with the final shape. "
            "Returns SUCCESS or ERROR. Fix errors and retry."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Full CadQuery Python code. Must assign final shape to 'result'."
                }
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]

# -----------------------
# ⚙️ Tool implementations
# -----------------------
def plan_design(object: str, dimensions: str, operations: list, notes: str = "") -> str:
    st.session_state.design_plan = {
        "object": object,
        "dimensions": dimensions,
        "operations": operations,
        "notes": notes,
    }
    return f"Plan saved: {object} | {dimensions} | {len(operations)} operations. Proceed to run_cadquery."


def run_cadquery(code: str) -> str:
    # Map common CSS color names → RGB floats that CadQuery/OCC accepts
    CSS_TO_RGB = {
        "darkgray": (0.66, 0.66, 0.66), "darkgrey": (0.66, 0.66, 0.66),
        "gray": (0.50, 0.50, 0.50),     "grey": (0.50, 0.50, 0.50),
        "lightgray": (0.83, 0.83, 0.83),"lightgrey": (0.83, 0.83, 0.83),
        "silver": (0.75, 0.75, 0.75),   "white": (1.0, 1.0, 1.0),
        "black": (0.0, 0.0, 0.0),       "red": (1.0, 0.0, 0.0),
        "green": (0.0, 0.5, 0.0),       "blue": (0.0, 0.0, 1.0),
        "yellow": (1.0, 1.0, 0.0),      "orange": (1.0, 0.65, 0.0),
        "cyan": (0.0, 1.0, 1.0),        "magenta": (1.0, 0.0, 1.0),
        "brown": (0.65, 0.16, 0.16),    "gold": (1.0, 0.84, 0.0),
        "darkblue": (0.0, 0.0, 0.55),   "darkred": (0.55, 0.0, 0.0),
        "darkgreen": (0.0, 0.39, 0.0),
    }

    # Patch cq.Color to accept CSS names by wrapping it
    original_color = cq.Color
    class SafeColor(original_color):
        def __init__(self, *args, **kwargs):
            if len(args) == 1 and isinstance(args[0], str):
                name = args[0].lower().replace(" ", "")
                if name in CSS_TO_RGB:
                    r, g, b = CSS_TO_RGB[name]
                    super().__init__(r, g, b)
                    return
            super().__init__(*args, **kwargs)

    try:
        local_vars = {}
        exec(code, {"cq": cq, "Color": SafeColor}, local_vars)
        result = local_vars.get("result")
        if result is None:
            return "ERROR: 'result' not defined. Assign your final CadQuery shape to 'result'."
        cq.exporters.export(result, STL_PATH)
        cq.exporters.export(result, STEP_PATH)
        st.session_state.last_code = code
        st.session_state.model_ready = True
        return "SUCCESS: Model saved as output.stl and output.step."
    except ValueError as e:
        if "Unknown color name" in str(e):
            return (
                f"ERROR: {e}. "
                "CadQuery does not accept CSS color names. "
                "Use RGB floats instead: cq.Color(0.5, 0.5, 0.5) for gray, etc."
            )
        return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: {e}"


def dispatch(name: str, args: dict) -> str:
    if name == "plan_design":
        return plan_design(**args)
    if name == "run_cadquery":
        return run_cadquery(args["code"])
    return f"Unknown tool: {name}"

# -----------------------
# 🧠 System Prompt
# -----------------------
SYSTEM_PROMPT = """You are IntelliCAD — an expert CAD assistant that generates precise 3D models using CadQuery.

═══════════════════════════════════════
DECISION: CLARIFY vs GENERATE
═══════════════════════════════════════

GENERATE IMMEDIATELY — no questions needed:
  • User gave explicit dimensions ("30mm cube", "cylinder 50mm diameter 100mm tall")
  • Simple primitives: box, sphere, cylinder, cone, torus
  • Modification of an existing model ("make it taller", "add a hole")
  • Standard objects with well-known defaults (a dice, a washer)

ASK FIRST — always clarify before generating:
  • Mechanical parts with critical dimensions: gears (teeth, module, pressure angle, bore),
    brackets (mounting pattern, load, wall thickness), springs, cams, pulleys
  • Objects with ambiguous size: "a shelf bracket" (how big? what load?)
  • Anything where a wrong dimension makes the model useless
  • Custom parts: "a phone stand" (which phone? angle? material thickness?)

HOW TO ASK:
  Be specific and brief. Ask only the 2-3 dimensions that matter most.
  Format: "Before I generate, I need a few dimensions:
  - Overall length?
  - Mounting hole diameter and spacing?
  - Wall thickness?"

═══════════════════════════════════════
WORKFLOW (once you have enough info)
═══════════════════════════════════════

Step 1 — RESEARCH (if needed)
  • Standard objects: web_search "M8 bolt ISO dimensions mm" BEFORE planning
  • Unsure about CadQuery syntax: web_search "cadquery <operation> example"
  • Never guess standard dimensions — always verify

Step 2 — PLAN (always)
  • Call plan_design with exact object name, all dimensions, and ordered operations
  • This locks down what you will build before touching code

Step 3 — GENERATE
  • Write clean CadQuery code from your plan
  • Call run_cadquery
  • On ERROR: read carefully, fix specifically, retry (max 4 times)
  • On SUCCESS: give a brief summary of what was built

═══════════════════════════════════════
CADQUERY RULES
═══════════════════════════════════════
  • Only 'cq' is available — import nothing else
  • Always assign final shape to 'result'
  • Use mm unless user says otherwise
  • Think in operations: extrude → cut → fillet → shell — plan the sequence first
  • Common mappings: donut/ring → torus | pipe/tube → hollow cylinder | slot → rectangle cut
  • Colors: NEVER use CSS names like "darkgray" or "red" — CadQuery rejects them.
    Always use RGB floats: cq.Color(0.66, 0.66, 0.66) for gray, cq.Color(1,0,0) for red, etc.

═══════════════════════════════════════
DESIGN QUALITY
═══════════════════════════════════════
  • Real objects need real proportions — search for them, don't invent them
  • Add details that make sense: fillets on sharp edges, chamfers on bolt heads
  • Think about manufacturability: wall thickness ≥ 2mm, no impossible geometry
  • After SUCCESS, tell the user: what was built, key dimensions used, any assumptions made

Off-topic questions: politely redirect to CAD modeling."""

# -----------------------
# 🤖 Agent Loop
# -----------------------
MAX_STEPS = 16


def run_agent(user_message: str, trace_box) -> tuple[str, bool]:
    input_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in st.session_state.messages[-10:]:
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

        # Show web search activity
        for item in response.output:
            if item.type == "web_search_call":
                action = getattr(item, "action", None)
                if action and hasattr(action, "query"):
                    queries = action.query if isinstance(action.query, list) else [action.query]
                    for q in queries:
                        trace_box.write(f"🔍 Searching: _{q}_")
                else:
                    trace_box.write("🔍 Searching the web...")

        # Check for custom function calls
        function_calls = [item for item in response.output if item.type == "function_call"]

        # No function calls → agent is done (either asked a question or finished)
        if not function_calls:
            for item in response.output:
                if item.type == "message":
                    text = "".join(
                        part.text for part in item.content if hasattr(part, "text")
                    )
                    return text, model_generated
            return "Done.", model_generated

        # Extend history with this turn's output
        input_messages.extend(response.output)

        # Execute each function call
        for fc in function_calls:
            args = json.loads(fc.arguments)

            if fc.name == "plan_design":
                trace_box.write(f"🗂 Planning: _{args.get('object', '')}_")
            elif fc.name == "run_cadquery":
                trace_box.write("⚙️ Running CadQuery code...")

            result = dispatch(fc.name, args)

            if fc.name == "run_cadquery":
                if result.startswith("SUCCESS"):
                    model_generated = True
                    trace_box.write("✅ Model generated!")
                else:
                    trace_box.write(f"⚠️ {result[:160]}")

            input_messages.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": result,
            })

    return "⚠️ Too many steps. Try a more specific request.", model_generated


# -----------------------
# 🚀 Main execution
# -----------------------
if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt

    with left:
        with st.chat_message("assistant"):
            with st.status("Agent working...", expanded=True) as status:
                final_response, model_generated = run_agent(prompt, status)
                if model_generated:
                    status.update(label="✅ Done!", state="complete", expanded=False)
                else:
                    status.update(label="💬 Replied", state="complete", expanded=False)

            st.markdown(final_response)

            if model_generated:
                col1, col2 = st.columns(2)
                with col1:
                    with open("output.step", "rb") as f:
                        st.download_button("⬇️ STEP", f, "model.step")
                with col2:
                    with open("output.stl", "rb") as f:
                        st.download_button("⬇️ STL", f, "model.stl")

    if model_generated:
        with viewer_placeholder.container():
            stl_from_file("output.stl", height=380)

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
    st.session_state.design_plan = None
    st.success("Reset complete")
    st.rerun()
