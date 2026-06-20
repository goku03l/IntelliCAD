import base64
import tempfile
import os
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
import cadquery as cq
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
    "stl_bytes": None,
    "step_bytes": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# -----------------------
# 🔍 Three.js STL Viewer (no external packages, works on Cloud)
# -----------------------
def stl_viewer(stl_bytes: bytes, height: int = 400):
    b64 = base64.b64encode(stl_bytes).decode()
    html = f"""
    <div id="stl-container" style="width:100%;height:{height}px;background:#1a1a2e;border-radius:8px;overflow:hidden;"></div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script>
    (function() {{
        var container = document.getElementById('stl-container');
        var scene = new THREE.Scene();
        scene.background = new THREE.Color(0x1a1a2e);

        var w = container.clientWidth || 600, h = {height};
        var camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100000);
        var renderer = new THREE.WebGLRenderer({{ antialias: true }});
        renderer.setSize(w, h);
        renderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(renderer.domElement);

        // Lights
        scene.add(new THREE.AmbientLight(0xffffff, 0.5));
        var d = new THREE.DirectionalLight(0xffffff, 0.8);
        d.position.set(1, 2, 3);
        scene.add(d);
        var d2 = new THREE.DirectionalLight(0x8888ff, 0.3);
        d2.position.set(-2, -1, -1);
        scene.add(d2);

        // Parse binary STL from base64
        var b64 = "{b64}";
        var bin = atob(b64);
        var buf = new ArrayBuffer(bin.length);
        var arr = new Uint8Array(buf);
        for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);

        var geo = new THREE.BufferGeometry();
        var view = new DataView(buf);
        var numTris = view.getUint32(80, true);
        var pos = new Float32Array(numTris * 9);
        var norm = new Float32Array(numTris * 9);
        var offset = 84;
        for (var t = 0; t < numTris; t++) {{
            var nx = view.getFloat32(offset, true);
            var ny = view.getFloat32(offset+4, true);
            var nz = view.getFloat32(offset+8, true);
            offset += 12;
            for (var v = 0; v < 3; v++) {{
                var base = t * 9 + v * 3;
                pos[base]   = view.getFloat32(offset, true);
                pos[base+1] = view.getFloat32(offset+4, true);
                pos[base+2] = view.getFloat32(offset+8, true);
                norm[base] = nx; norm[base+1] = ny; norm[base+2] = nz;
                offset += 12;
            }}
            offset += 2; // attribute byte count
        }}
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        geo.setAttribute('normal', new THREE.BufferAttribute(norm, 3));

        var mat = new THREE.MeshPhongMaterial({{
            color: 0x00d4ff, specular: 0x222244, shininess: 60,
            side: THREE.DoubleSide
        }});
        var mesh = new THREE.Mesh(geo, mat);
        scene.add(mesh);

        // Center + fit camera
        geo.computeBoundingBox();
        var box = geo.boundingBox;
        var cx = (box.max.x + box.min.x) / 2;
        var cy = (box.max.y + box.min.y) / 2;
        var cz = (box.max.z + box.min.z) / 2;
        mesh.position.set(-cx, -cy, -cz);
        var size = Math.max(
            box.max.x - box.min.x,
            box.max.y - box.min.y,
            box.max.z - box.min.z
        );
        camera.position.set(0, 0, size * 2);
        camera.near = size * 0.001;
        camera.far  = size * 100;
        camera.updateProjectionMatrix();

        // Orbit controls (mouse drag)
        var isDragging = false, prevX = 0, prevY = 0, rotX = 0, rotY = 0;
        var zoom = 1.0;
        renderer.domElement.addEventListener('mousedown', function(e) {{
            isDragging = true; prevX = e.clientX; prevY = e.clientY;
        }});
        window.addEventListener('mouseup', function() {{ isDragging = false; }});
        window.addEventListener('mousemove', function(e) {{
            if (!isDragging) return;
            rotY += (e.clientX - prevX) * 0.01;
            rotX += (e.clientY - prevY) * 0.01;
            prevX = e.clientX; prevY = e.clientY;
        }});
        renderer.domElement.addEventListener('wheel', function(e) {{
            zoom *= (1 + e.deltaY * 0.001);
            zoom = Math.max(0.1, Math.min(10, zoom));
        }});

        function animate() {{
            requestAnimationFrame(animate);
            mesh.rotation.x = rotX;
            mesh.rotation.y = rotY;
            camera.position.z = size * 2 * zoom;
            renderer.render(scene, camera);
        }}
        animate();
    }})();
    </script>
    """
    components.html(html, height=height + 10)

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
        if st.session_state.model_ready and st.session_state.stl_bytes:
            stl_viewer(st.session_state.stl_bytes, height=380)
        else:
            st.image("icon.png", width="stretch")

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
    # CSS color names CadQuery/OCC doesn't accept
    CSS_COLORS = {
        "darkgray": (0.66,0.66,0.66), "darkgrey": (0.66,0.66,0.66),
        "gray": (0.50,0.50,0.50),     "grey": (0.50,0.50,0.50),
        "lightgray": (0.83,0.83,0.83),"lightgrey": (0.83,0.83,0.83),
        "silver": (0.75,0.75,0.75),   "white": (1.0,1.0,1.0),
        "black": (0.0,0.0,0.0),       "red": (1.0,0.0,0.0),
        "green": (0.0,0.5,0.0),       "blue": (0.0,0.0,1.0),
        "yellow": (1.0,1.0,0.0),      "orange": (1.0,0.65,0.0),
        "cyan": (0.0,1.0,1.0),        "magenta": (1.0,0.0,1.0),
        "brown": (0.65,0.16,0.16),    "gold": (1.0,0.84,0.0),
        "darkblue": (0.0,0.0,0.55),   "darkred": (0.55,0.0,0.0),
        "darkgreen": (0.0,0.39,0.0),
    }
    OrigColor = cq.Color
    class SafeColor(OrigColor):
        def __init__(self, *args, **kwargs):
            if len(args) == 1 and isinstance(args[0], str):
                name = args[0].lower().replace(" ", "")
                if name in CSS_COLORS:
                    r, g, b = CSS_COLORS[name]
                    super().__init__(r, g, b)
                    return
            super().__init__(*args, **kwargs)

    try:
        local_vars = {}
        cq_env = cq
        cq_env.Color = SafeColor
        exec(code, {"cq": cq_env}, local_vars)
        result = local_vars.get("result")
        if result is None:
            return "ERROR: 'result' not defined. Assign your final CadQuery shape to 'result'."

        # Export to tempfiles (always writable, even on Streamlit Cloud)
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            stl_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            step_path = f.name

        cq.exporters.export(result, stl_path)
        cq.exporters.export(result, step_path)

        with open(stl_path, "rb") as f:
            st.session_state.stl_bytes = f.read()
        with open(step_path, "rb") as f:
            st.session_state.step_bytes = f.read()

        os.unlink(stl_path)
        os.unlink(step_path)

        st.session_state.last_code = code
        st.session_state.model_ready = True
        return "SUCCESS: Model generated successfully."

    except ValueError as e:
        if "Unknown color name" in str(e):
            return f"ERROR: {e}. Use RGB floats: cq.Color(0.5, 0.5, 0.5) — never CSS color name strings."
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
  • Colors: NEVER use CSS names like "darkgray" — use RGB floats: cq.Color(0.66, 0.66, 0.66)
  • NEVER mention or link to output.stl or output.step — the viewer and download buttons handle this

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

        for item in response.output:
            if item.type == "web_search_call":
                action = getattr(item, "action", None)
                if action and hasattr(action, "query"):
                    queries = action.query if isinstance(action.query, list) else [action.query]
                    for q in queries:
                        trace_box.write(f"🔍 Searching: _{q}_")
                else:
                    trace_box.write("🔍 Searching the web...")

        function_calls = [item for item in response.output if item.type == "function_call"]

        if not function_calls:
            for item in response.output:
                if item.type == "message":
                    text = "".join(
                        part.text for part in item.content if hasattr(part, "text")
                    )
                    return text, model_generated
            return "Done.", model_generated

        input_messages.extend(response.output)

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
                    st.download_button("⬇️ STEP", st.session_state.step_bytes, "model.step")
                with col2:
                    st.download_button("⬇️ STL", st.session_state.stl_bytes, "model.stl")

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
    st.session_state.stl_bytes = None
    st.session_state.step_bytes = None
    st.success("Reset complete")
    st.rerun()
