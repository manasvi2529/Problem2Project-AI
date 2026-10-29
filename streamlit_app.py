"""
Problem2Project AI — Conversational Autonomous LLM Agent Studio.

An interactive AI Agent chat interface that:
1. Dynamically detects your Computer Science domain (SaaS/Web, AI/ML, Data Science, DevOps, Cybersecurity)
2. Fetches live, unfeeded real-world data from Kaggle, Reddit, HackerNews & StackOverflow in parallel
3. Outputs both: (A) The Real Discovered Problems, and (B) The Paired Startup Opportunities with domain-tailored tech stacks
4. Acts as a talking conversational assistant (with Voice Narration / Text-to-Speech)
5. Requests human permission before creating repositories and deploying applications
"""
import asyncio
import os
import re
import json
import time
from datetime import datetime
from typing import List, Dict, Any

import streamlit as st

# Backend Services
from backend.services.platform_scrapers import scrape_all_platforms
from backend.services.llm_agent import LLMAgent, CS_DOMAINS, detect_domain_from_text
from backend.services.project_deployer import ProjectDeployer
from backend.config import settings

# ── Streamlit Page Configuration ─────────────────────────────────────────────
st.set_page_config(
    page_title="Problem2Project AI — Conversational LLM Studio",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown("""
<style>
    .chat-header {
        font-size: 1.8rem;
        font-weight: 800;
        background: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.1rem;
    }
    .tool-call-box {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 8px;
        padding: 0.6rem 0.9rem;
        font-family: monospace;
        font-size: 0.85rem;
        color: #818cf8;
        margin: 0.5rem 0;
    }
    .problem-item {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 6px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
    }
    .problem-solution-card {
        background: rgba(30, 41, 59, 0.7);
        border-left: 4px solid #6366f1;
        border-radius: 8px;
        padding: 1.1rem;
        margin: 0.8rem 0;
    }
    .card-selected {
        border-left: 4px solid #10b981 !important;
        background: rgba(16, 185, 129, 0.08) !important;
    }
    .permission-box {
        background: rgba(30, 41, 59, 0.9);
        border: 2px solid #f59e0b;
        border-radius: 10px;
        padding: 1.25rem;
        margin: 1rem 0;
    }
    .voice-btn {
        background: rgba(99, 102, 241, 0.2);
        border: 1px solid #6366f1;
        color: #a5b4fc;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        cursor: pointer;
        display: inline-block;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# ── Session State Initialization ─────────────────────────────────────────────
if "domain_key" not in st.session_state:
    st.session_state.domain_key = "fullstack_web"

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 **Hello! I am your Autonomous Computer Science & Startup AI Co-Founder.**\n\n"
                "I scan live, unfeeded real-world discussions from **Kaggle, Reddit, Hacker News, and Stack Overflow** "
                "to find real pain points people are struggling with, match them to your Computer Science domain, "
                "and with your permission, write the full code, initialize a Git repository, and deploy the application live.\n\n"
                "**What would you like to build or explore?**\n"
                "- *\"Find SaaS customer onboarding and billing pain points on Reddit\"*\n"
                "- *\"I am focusing on Machine Learning & NLP. What real-world startups can I build?\"*\n"
                "- *\"I do Data Science. Look up real dataset challenges on Kaggle.\"*\n"
                "- *\"Find Docker and DevOps infrastructure headaches.\"*"
            ),
        }
    ]

if "pending_permission" not in st.session_state:
    st.session_state.pending_permission = None

if "last_opportunities" not in st.session_state:
    st.session_state.last_opportunities = []

if "last_problems_found" not in st.session_state:
    st.session_state.last_problems_found = []

if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = True

def run_async(coro):
    return asyncio.run(coro)


# ── Sidebar Controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎓 Current CS Domain")

    domain_keys = list(CS_DOMAINS.keys())
    current_idx = domain_keys.index(st.session_state.domain_key) if st.session_state.domain_key in domain_keys else 0

    selected_domain = st.selectbox(
        "Domain Focus:",
        options=domain_keys,
        format_func=lambda k: CS_DOMAINS[k]["name"],
        index=current_idx,
    )
    st.session_state.domain_key = selected_domain
    domain_info = CS_DOMAINS[selected_domain]

    st.markdown(f"**Target Tech Stack:**")
    st.code(", ".join(domain_info["recommended_stack"]), language="text")

    st.markdown("---")
    st.markdown("### 🎙️ Talking Chatbot Voice")
    st.session_state.voice_enabled = st.checkbox("🔊 Enable Audio Speech Synthesis", value=st.session_state.voice_enabled)

    st.markdown("---")
    st.markdown("### 🌐 Live Data Sources")
    sub_reddit = st.checkbox("Reddit (r/startups, r/datascience, r/SaaS)", value=True)
    sub_kaggle = st.checkbox("Kaggle (Problem Datasets & Challenges)", value=True)
    sub_hn = st.checkbox("Hacker News (Ask HN, Show HN)", value=True)
    sub_so = st.checkbox("Stack Overflow", value=True)
    sub_devto = st.checkbox("Dev.to", value=True)

    active_platforms = []
    if sub_reddit: active_platforms.append("reddit")
    if sub_kaggle: active_platforms.append("kaggle")
    if sub_hn: active_platforms.append("hackernews")
    if sub_so: active_platforms.append("stackoverflow")
    if sub_devto: active_platforms.append("devto")

    st.markdown("---")
    st.markdown("### 🧠 OpenRouter Configuration")
    user_api_key = st.text_input(
        "OpenRouter API Key (Optional):",
        value=settings.OPENROUTER_API_KEY or "",
        type="password",
        help="Optional: Enter key to query Llama 3.3 70B, Claude, or Mistral. If blank, our Python autonomous engine runs locally!",
    )
    user_model = st.selectbox(
        "Model:",
        options=[
            "meta-llama/llama-3.3-70b-instruct",
            "anthropic/claude-3.5-sonnet",
            "mistralai/mistral-large",
            "google/gemini-flash-1.5",
        ],
        index=0,
    )

    st.markdown("---")
    st.markdown("### 🐙 GitHub Account Sync (Optional)")
    github_token = st.text_input(
        "GitHub Token (Optional):",
        value="",
        type="password",
        help="Optional: If entered, the agent will also create a remote repository on github.com and push to it. Otherwise, it initializes the repository locally on your machine!",
    )

    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = [st.session_state.messages[0]]
        st.session_state.pending_permission = None
        st.session_state.last_opportunities = []
        st.session_state.last_problems_found = []
        st.rerun()


# ── Header with Voice Toggle ─────────────────────────────────────────────────
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown('<div class="chat-header">Problem2Project AI — Conversational LLM Studio</div>', unsafe_allow_html=True)
    st.caption(f"Domain: **{domain_info['name']}** &bull; Sources: {', '.join(active_platforms)}")
with header_col2:
    st.session_state.voice_enabled = st.toggle("🗣️ Talking Voice Mode", value=st.session_state.voice_enabled)


# ── Quick Prompt Chips ───────────────────────────────────────────────────────
col_q1, col_q2, col_q3, col_q4 = st.columns(4)
quick_prompt = None
with col_q1:
    if st.button("🌐 SaaS Web Apps", use_container_width=True):
        quick_prompt = "Find customer onboarding, churn, and billing SaaS pain points on Reddit"
with col_q2:
    if st.button("🤖 AI / NLP Startups", use_container_width=True):
        quick_prompt = "Find real-world startup problems for Artificial Intelligence and NLP"
with col_q3:
    if st.button("📊 Kaggle Data Problems", use_container_width=True):
        quick_prompt = "Search Kaggle and Reddit for data science problem datasets"
with col_q4:
    if st.button("☁️ DevOps Friction", use_container_width=True):
        quick_prompt = "Find Docker, CI/CD, and cloud infrastructure headaches"


# ── Render Chat History ──────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)


# ── Voice Synthesis Helper ───────────────────────────────────────────────────
def trigger_voice_speak(text: str):
    """Play speech audio using browser Web Speech API with safe escaping."""
    if not st.session_state.voice_enabled or not text:
        return
    clean_speech = re.sub(r"[#*_`\[\]\(\)\<\>]", " ", text[:280])
    clean_speech = clean_speech.replace('"', '\\"').replace("'", "\\'").replace('\n', ' ').strip()
    js_code = f"""
    <script>
        (function() {{
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                const utterance = new SpeechSynthesisUtterance("{clean_speech}");
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                window.speechSynthesis.speak(utterance);
            }}
        }})();
    </script>
    """
    st.components.v1.html(js_code, height=0)


# ── Interactive Opportunity Selection & Permission Quick Actions ─────────────
if st.session_state.last_opportunities and not st.session_state.pending_permission:
    st.markdown("##### 🎯 Click to Choose an Opportunity:")
    q_col1, q_col2, q_col3 = st.columns(3)
    for i, opp in enumerate(st.session_state.last_opportunities[:3]):
        with [q_col1, q_col2, q_col3][i]:
            if st.button(f"👉 Pick #{i+1}: {opp['title'][:25]}...", key=f"quick_pick_{i+1}", use_container_width=True):
                quick_prompt = f"I want opportunity {i+1}"

if st.session_state.pending_permission:
    st.markdown("##### 🛡️ Ready to Build:")
    if st.button(f"🚀 Approve & Launch '{st.session_state.pending_permission['title']}' on Port 8020", type="primary", use_container_width=True):
        quick_prompt = "Approve"


# ── Handle Input (Chat or Quick Chip / Button) ───────────────────────────────
user_input = st.chat_input("Ask about problems, choose an opportunity (e.g. 'I want opportunity 3'), or type 'Approve'...") or quick_prompt

if user_input:
    # Auto-detect domain only if an explicit domain switch keyword was typed
    detected = detect_domain_from_text(user_input)
    if detected:
        st.session_state.domain_key = detected

    active_domain_key = st.session_state.domain_key
    domain_info = CS_DOMAINS[active_domain_key]

    # 1. Add user message to chat
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    agent = LLMAgent(api_key=user_api_key, model=user_model)

    # 2. Understand user intent with LLM
    with st.spinner("AI understanding your request..."):
        intent_data = run_async(agent.understand_user_intent(
            user_message=user_input,
            available_opportunities=st.session_state.last_opportunities,
            pending_permission_opp=st.session_state.pending_permission,
            domain_name=domain_info["name"],
        ))

    intent = intent_data.get("intent", "search_new_topic")
    opp_idx = intent_data.get("opportunity_index")
    explanation = intent_data.get("explanation_answer", "")

    # ── CASE A: USER SELECTED A SPECIFIC OPPORTUNITY (e.g. "I want opportunity 3") ──
    if intent == "select_opportunity" and opp_idx and opp_idx <= len(st.session_state.last_opportunities):
        target_opp = st.session_state.last_opportunities[opp_idx - 1]
        st.session_state.pending_permission = target_opp

        with st.chat_message("assistant"):
            st.markdown(explanation, unsafe_allow_html=True)

            card_html = f"""
<div class="problem-solution-card card-selected">
    <div style="color: #10b981; font-weight: 700; font-size: 0.85rem;">SELECTED TARGET: OPPORTUNITY #{opp_idx} &bull; {target_opp['cs_domain']}</div>
    <h3 style="margin: 0.3rem 0; color: #f8fafc;">{target_opp['title']}</h3>
    <p><strong>🎯 Real Problem:</strong> {target_opp['problem']}</p>
    <p><strong>🚀 Startup Solution:</strong> {target_opp['solution']}</p>
    <p style="font-size: 0.85rem; color: #94a3b8;">
        <strong>Recommended Stack:</strong> <code>{', '.join(target_opp.get('tech_stack', []))}</code> &bull; 
        <strong>Evidence:</strong> {target_opp.get('evidence_citation', 'Live Community')}
    </p>
</div>

<div class="permission-box">
    <h4 style="margin: 0 0 0.5rem 0; color: #f59e0b;">🛡️ Human-in-the-Loop Permission Request for Opportunity #{opp_idx}</h4>
    <p style="margin: 0; color: #e2e8f0; font-size: 0.9rem;">
        Would you like me to build and deploy <strong>"{target_opp['title']}"</strong>?<br>
        I will create a local Git repository on your drive at <code>data/sandboxes/</code>, generate <code>index.html</code>, <code>styles.css</code>, <code>app.js</code>, and <code>server.py</code>, and launch it on <code>http://localhost:8020</code>.<br><br>
        <strong>Type "Approve" in the chat to launch!</strong>
    </p>
</div>
"""
            st.markdown(card_html, unsafe_allow_html=True)
            trigger_voice_speak(f"Selected Opportunity number {opp_idx}: {target_opp['title']}. Ready to build and deploy whenever you say approve.")

            st.session_state.messages.append({
                "role": "assistant",
                "content": explanation + "\n\n" + card_html,
            })
            st.rerun()

    # ── CASE B: USER ASKED A QUESTION (e.g. Git vs GitHub or API Key doubt) ────────
    elif intent == "question":
        with st.chat_message("assistant"):
            st.markdown(explanation, unsafe_allow_html=True)
            trigger_voice_speak(explanation[:200])
            st.session_state.messages.append({"role": "assistant", "content": explanation})
            st.rerun()

    # ── CASE C: USER GRANTED APPROVAL (e.g. "Approve", "Deploy", "Yes") ──────────
    elif intent == "approve_deployment":
        pending = st.session_state.pending_permission
        if not pending and st.session_state.last_opportunities:
            pending = st.session_state.last_opportunities[0]

        if pending:
            with st.chat_message("assistant"):
                st.markdown(f'<div class="tool-call-box">⚙️ [EXECUTION TOOL] Permission granted! Generating full-stack code and initializing Git repository for <strong>{pending["title"]}</strong>...</div>', unsafe_allow_html=True)

                with st.spinner("Synthesizing code files, initializing Git repo, and deploying..."):
                    try:
                        files = run_async(agent.generate_application_files(
                            problem=pending["problem"],
                            solution=pending["solution"],
                            cs_domain=pending["cs_domain"],
                            project_name=pending["title"],
                        ))

                        slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in pending["title"][:25]).lower()
                        deploy_result = ProjectDeployer.deploy_application(
                            project_name=slug,
                            files=files,
                            preferred_port=8020,
                        )

                        reply_text = f"""### 🎉 Application Successfully Deployed!

- **Project:** `{pending['title']}`
- **Tech Stack:** `{', '.join(pending.get('tech_stack', []))}`
- **Repository Path:** `data/sandboxes/{deploy_result['project_name']}`
- **Git Commit:** `{deploy_result['git_commit']}` (Initialized locally & committed)
- **Files Created:** `{', '.join(deploy_result['files_created'])}`
- **Live Local URL:** **[{deploy_result['url']}]({deploy_result['url']})**

---
#### 🖥️ Interactive Web Preview:
"""
                        st.markdown(reply_text)
                        st.components.v1.iframe(deploy_result["url"], height=480, scrolling=True)
                        trigger_voice_speak(f"Your application {pending['title']} has been successfully built and deployed on port 8020.")

                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": reply_text,
                        })

                    except Exception as e:
                        err_msg = f"❌ Deployment failed: {str(e)}"
                        st.error(err_msg)
                        st.session_state.messages.append({"role": "assistant", "content": err_msg})
        else:
            with st.chat_message("assistant"):
                no_opp_msg = "Please search for a topic or choose an opportunity first, and I will be happy to build and deploy it!"
                st.markdown(no_opp_msg)
                st.session_state.messages.append({"role": "assistant", "content": no_opp_msg})

    # ── CASE D: NEW RESEARCH TOPIC SEARCH ────────────────────────────────────────
    else:
        search_query = intent_data.get("search_query") or user_input
        with st.chat_message("assistant"):
            st.markdown(f'<div class="tool-call-box">🔍 [TOOL: LIVE SCRAPER] Querying {", ".join(active_platforms)} in parallel for "{search_query}" (Domain: {domain_info["name"]})...</div>', unsafe_allow_html=True)

            with st.spinner("Scraping live data across Kaggle, Reddit & Hacker News in parallel..."):
                t0 = time.time()
                scraped = run_async(scrape_all_platforms(search_query, active_platforms))
                items = []
                for p_name, p_items in scraped["results"].items():
                    items.extend(p_items)
                elapsed = round(time.time() - t0, 1)

            st.markdown(f'<div class="tool-call-box">⚡ [DATA SCIENCE] Ingested {len(items)} live discussions in {elapsed}s across {len(scraped["results"])} platforms.</div>', unsafe_allow_html=True)

            if not items:
                reply = "I couldn't find any live discussions for that keyword. Could you try a broader topic (e.g. *customer churn*, *data pipelines*, *billing*, *medical*)?"
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            else:
                st.markdown(f'<div class="tool-call-box">🧠 [LLM SYNTHESIS] Pairing live problems with {domain_info["name"]} solutions & stack: {", ".join(domain_info["recommended_stack"])}...</div>', unsafe_allow_html=True)

                with st.spinner("Synthesizing validated Problem + Solution blueprints..."):
                    opps = run_async(agent.synthesize_domain_opportunities(active_domain_key, items, num_opportunities=3))
                    st.session_state.last_opportunities = opps
                    st.session_state.last_problems_found = items[:5]

                # 1. RENDER RAW PROBLEMS SECTION
                problems_html = f"### 📋 1. Real-World Problems Discovered Live ({len(items)} discussions ingested)\n"
                for p_it in items[:4]:
                    plat = p_it.get("platform", "community").upper()
                    problems_html += f"""
<div class="problem-item">
    <span style="background: rgba(99, 102, 241, 0.2); color: #818cf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">{plat}</span>
    <strong style="margin-left: 6px;"><a href="{p_it.get('url', '#')}" target="_blank" style="color: #f1f5f9; text-decoration: none;">{p_it.get('title')}</a></strong>
    <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 4px;">Score / Upvotes: {p_it.get('score', 0)} &bull; {p_it.get('content', '')[:140]}...</div>
</div>
"""

                # 2. RENDER PAIRED OPPORTUNITIES SECTION
                opps_html = f"\n### 🚀 2. Paired Startup & Project Opportunities ({domain_info['name']})\n"
                for idx, opp in enumerate(opps):
                    opps_html += f"""
<div class="problem-solution-card">
    <div style="color: #818cf8; font-weight: 700; font-size: 0.8rem;">OPPORTUNITY #{idx+1} &bull; {opp['cs_domain']}</div>
    <h3 style="margin: 0.3rem 0; color: #f8fafc;">{opp['title']}</h3>
    <p><strong>🎯 Real Problem:</strong> {opp['problem']}</p>
    <p><strong>🚀 Startup Solution:</strong> {opp['solution']}</p>
    <p style="font-size: 0.85rem; color: #94a3b8;">
        <strong>Recommended Tech Stack:</strong> <code>{', '.join(opp.get('tech_stack', []))}</code><br>
        <strong>Market Viability:</strong> {opp.get('market_viability', 'High community demand.')}
    </p>
</div>
"""

                prompt_guide = (
                    "\n👉 **Which opportunity would you like to build?**\n"
                    "- Type *\"I want opportunity 1\"*, *\"I want opportunity 2\"*, or *\"I want opportunity 3\"*.\n"
                    "- Or ask me any question about the architecture or how the repository will be created!"
                )

                full_content = problems_html + opps_html + prompt_guide
                st.markdown(full_content, unsafe_allow_html=True)
                trigger_voice_speak(f"I found {len(items)} real-world discussions and synthesized 3 project opportunities for {domain_info['name']}. Which one would you like to build?")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_content,
                })
                st.rerun()
