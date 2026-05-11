"""
frontend/app.py — Streamlit UI for the AI Proposal Generator.

Pages (sidebar navigation):
  ✏️  Generate      — Submit inputs, watch generation, preview & edit sections
  📋  History       — Browse past proposals, re-download exports
  🏢  Company       — Manage reusable company profiles
  📝  Templates     — Live-edit prompt templates (no restart needed)
  ℹ️  About         — App info and API status

Run with:
    streamlit run frontend/app.py
"""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests
import streamlit as st

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"
POLL_INTERVAL = 2          # seconds between status polls
MAX_POLL_ATTEMPTS = 90     # 3 minutes timeout

SECTION_LABELS = {
    "executive_summary":  "📋 Executive Summary",
    "technical_approach": "⚙️  Technical Approach",
    "milestones":         "🗓️  Project Milestones",
    "estimated_timeline": "⏱️  Estimated Timeline",
    "pricing_structure":  "💰 Pricing Structure",
    "risks":              "⚠️  Risk Assessment",
    "deliverables":       "📦 Deliverables",
    "next_steps":         "🚀 Next Steps",
}

TONE_OPTIONS = {
    "professional": "🤝 Professional — Formal and authoritative",
    "friendly":     "😊 Friendly — Warm and conversational",
    "technical":    "🔧 Technical — Detailed and engineering-focused",
    "executive":    "👔 Executive — Concise and outcome-driven",
}

SECTION_TEMPLATE_MAP = {
    "system":             "System Prompt (base)",
    "executive_summary":  "Executive Summary",
    "technical_approach": "Technical Approach",
    "milestones":         "Project Milestones",
    "pricing_structure":  "Pricing Structure",
    "risks":              "Risk Assessment",
    "deliverables":       "Deliverables",
    "next_steps":         "Next Steps",
}


# ── API helpers ────────────────────────────────────────────────────────────────

def api_get(path: str, **kwargs) -> Optional[dict]:
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=10, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot reach the backend. Is it running? (`uvicorn backend.main:app --reload`)")
        return None
    except requests.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
        return None


def api_post(path: str, json: dict) -> Optional[dict]:
    try:
        r = requests.post(f"{API_BASE}{path}", json=json, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot reach the backend.")
        return None
    except requests.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
        return None


def api_patch(path: str, json: dict) -> Optional[dict]:
    try:
        r = requests.patch(f"{API_BASE}{path}", json=json, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Patch failed: {e}")
        return None


def api_delete(path: str) -> bool:
    try:
        r = requests.delete(f"{API_BASE}{path}", timeout=10)
        return r.status_code == 204
    except Exception:
        return False


def download_file(path: str) -> Optional[bytes]:
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=30)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


# ── Page: Generate ─────────────────────────────────────────────────────────────

def page_generate():
    st.title("✏️ Generate Proposal")
    st.markdown("Fill in the client details below. The AI will generate a full proposal in ~60–90 seconds.")

    # Load profiles for dropdown
    profiles_data = api_get("/api/profiles")
    profile_options = {"None (no company profile)": None}
    if profiles_data:
        for p in profiles_data.get("items", []):
            profile_options[f"{p['company_name']} {'⭐' if p['is_default'] else ''}"] = p["id"]

    with st.form("proposal_form", clear_on_submit=False):
        col1, col2 = st.columns(2)

        with col1:
            client_name = st.text_input(
                "Client Name *",
                placeholder="e.g. Acme Corporation",
                help="Name of the client or organisation",
            )
            budget = st.text_input(
                "Budget *",
                placeholder="e.g. $50,000 – $75,000",
                help="Budget range or fixed amount",
            )
            timeline = st.text_input(
                "Timeline *",
                placeholder="e.g. 4 months",
                help="Expected project duration",
            )

        with col2:
            tone_key = st.selectbox(
                "Proposal Tone *",
                options=list(TONE_OPTIONS.keys()),
                format_func=lambda k: TONE_OPTIONS[k],
                help="Writing style for the generated proposal",
            )
            selected_profile_label = st.selectbox(
                "Company Profile",
                options=list(profile_options.keys()),
                help="Inject your company's details into the proposal",
            )

        project_description = st.text_area(
            "Project Description *",
            placeholder="Describe what the project involves — the more detail, the better the proposal.",
            height=120,
        )
        goals = st.text_area(
            "Goals & Success Criteria *",
            placeholder="What does success look like? Include KPIs, business outcomes, or requirements.",
            height=100,
        )

        submitted = st.form_submit_button("🚀 Generate Proposal", type="primary", use_container_width=True)

    if submitted:
        # Validate
        errors = []
        if not client_name.strip():
            errors.append("Client Name is required")
        if not project_description.strip() or len(project_description.strip()) < 20:
            errors.append("Project Description must be at least 20 characters")
        if not budget.strip():
            errors.append("Budget is required")
        if not timeline.strip():
            errors.append("Timeline is required")
        if not goals.strip() or len(goals.strip()) < 10:
            errors.append("Goals must be at least 10 characters")

        if errors:
            for e in errors:
                st.error(f"⚠️ {e}")
            return

        payload = {
            "client_name": client_name.strip(),
            "project_description": project_description.strip(),
            "budget": budget.strip(),
            "timeline": timeline.strip(),
            "goals": goals.strip(),
            "tone": tone_key,
            "company_profile_id": profile_options[selected_profile_label],
        }

        with st.spinner("Submitting..."):
            result = api_post("/api/proposals/generate", payload)

        if not result:
            return

        proposal_id = result["proposal_id"]
        st.success(f"✅ Generation started! Proposal ID: `{proposal_id}`")
        st.session_state["active_proposal_id"] = proposal_id
        st.session_state["active_proposal_data"] = payload

        # Poll for completion
        progress_bar = st.progress(0, text="⏳ Generating your proposal…")
        status_placeholder = st.empty()

        for attempt in range(MAX_POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL)
            status_data = api_get(f"/api/proposals/{proposal_id}")
            if not status_data:
                break

            current_status = status_data.get("status")
            progress = min(0.95, (attempt + 1) / MAX_POLL_ATTEMPTS)
            progress_bar.progress(progress, text=f"⏳ Status: **{current_status}** — attempt {attempt + 1}")

            if current_status == "completed":
                progress_bar.progress(1.0, text="✅ Generation complete!")
                status_placeholder.empty()
                st.session_state["completed_proposal"] = status_data
                st.balloons()
                _render_proposal(status_data)
                return
            elif current_status == "failed":
                progress_bar.empty()
                st.error(f"❌ Generation failed: {status_data.get('error_message', 'Unknown error')}")
                return

        st.warning("⏰ Generation is taking longer than expected. Check the History tab for results.")

    # If we have a completed proposal in session, show it
    elif "completed_proposal" in st.session_state:
        _render_proposal(st.session_state["completed_proposal"])


def _render_proposal(proposal: dict):
    """Render the completed proposal with expandable sections and export buttons."""
    st.divider()
    st.subheader(f"📄 Proposal for {proposal['client_name']}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Budget", proposal["budget"])
    col2.metric("Timeline", proposal["timeline"])
    col3.metric("Tone", proposal["tone"].capitalize())
    dur = proposal.get("generation_duration_ms")
    col4.metric("Generated in", f"{dur // 1000}s" if dur else "—")

    st.divider()

    # Render each section
    for field, label in SECTION_LABELS.items():
        content = proposal.get(field)
        if not content:
            continue

        with st.expander(label, expanded=(field == "executive_summary")):
            # Editable text area
            edited_key = f"edit_{field}_{proposal['id']}"
            if edited_key not in st.session_state:
                st.session_state[edited_key] = content

            edited = st.text_area(
                "Content (editable)",
                value=st.session_state[edited_key],
                height=300,
                key=f"ta_{field}_{proposal['id']}",
                label_visibility="collapsed",
            )
            st.session_state[edited_key] = edited

            col_a, col_b = st.columns([1, 4])
            if col_a.button("🔄 Regenerate", key=f"regen_{field}_{proposal['id']}"):
                with st.spinner(f"Regenerating {label}…"):
                    result = api_get(
                        f"/api/proposals/{proposal['id']}/regenerate",
                        params={"section": field},
                    )
                    # Note: this is a POST in the real API — using requests directly
                    r = requests.post(
                        f"{API_BASE}/api/proposals/{proposal['id']}/regenerate",
                        params={"section": field},
                        timeout=60,
                    )
                    if r.status_code == 200:
                        new_content = r.json().get("content", "")
                        st.session_state[edited_key] = new_content
                        st.success("Section regenerated!")
                        st.rerun()
                    else:
                        st.error(f"Regeneration failed: {r.text}")

    # Export buttons
    st.divider()
    st.subheader("📥 Export")
    pid = proposal["id"]
    col_md, col_pdf, col_json = st.columns(3)

    with col_md:
        md_bytes = download_file(f"/api/export/{pid}/markdown")
        if md_bytes:
            st.download_button(
                "⬇️ Download Markdown",
                data=md_bytes,
                file_name=f"proposal_{proposal['client_name'].replace(' ', '_')}.md",
                mime="text/markdown",
                use_container_width=True,
            )

    with col_pdf:
        pdf_bytes = download_file(f"/api/export/{pid}/pdf")
        if pdf_bytes:
            st.download_button(
                "⬇️ Download PDF",
                data=pdf_bytes,
                file_name=f"proposal_{proposal['client_name'].replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

    with col_json:
        json_bytes = download_file(f"/api/export/{pid}/json")
        if json_bytes:
            st.download_button(
                "⬇️ Download JSON",
                data=json_bytes,
                file_name=f"proposal_{proposal['client_name'].replace(' ', '_')}.json",
                mime="application/json",
                use_container_width=True,
            )


# ── Page: History ──────────────────────────────────────────────────────────────

def page_history():
    st.title("📋 Proposal History")

    col_refresh, col_filter = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.rerun()
    with col_filter:
        status_filter = st.selectbox(
            "Filter by status",
            ["All", "completed", "pending", "generating", "failed"],
            label_visibility="collapsed",
        )

    params = {} if status_filter == "All" else {"status": status_filter}
    data = api_get("/api/proposals", **{"params": params} if params else {})
    if not data:
        return

    proposals = data.get("items", [])
    if not proposals:
        st.info("No proposals found. Generate your first one!")
        return

    st.caption(f"{data['total']} proposal(s) found")

    for p in proposals:
        status_icon = {
            "completed": "✅",
            "pending": "⏳",
            "generating": "⚙️",
            "failed": "❌",
        }.get(p["status"], "❓")

        with st.expander(
            f"{status_icon} **{p['client_name']}** — {p['budget']} — {p['timeline']} "
            f"— `{p['id'][:8]}…`",
            expanded=False,
        ):
            col1, col2, col3 = st.columns(3)
            col1.write(f"**Status:** {p['status']}")
            col2.write(f"**Tone:** {p['tone']}")
            dur = p.get("generation_duration_ms")
            col3.write(f"**Duration:** {dur // 1000}s" if dur else "**Duration:** —")

            st.caption(f"Created: {p['created_at'][:19].replace('T', ' ')} UTC")
            st.write(f"**Description:** {p['project_description'][:200]}…")

            col_view, col_md, col_pdf, col_json, col_del = st.columns(5)

            if p["status"] == "completed":
                if col_view.button("👁️ View", key=f"view_{p['id']}"):
                    full = api_get(f"/api/proposals/{p['id']}")
                    if full:
                        st.session_state["completed_proposal"] = full
                        st.session_state["page"] = "✏️ Generate"
                        st.rerun()

                md_bytes = download_file(f"/api/export/{p['id']}/markdown")
                if md_bytes:
                    col_md.download_button(
                        "📄 MD",
                        data=md_bytes,
                        file_name=f"proposal_{p['id'][:8]}.md",
                        mime="text/markdown",
                        key=f"md_{p['id']}",
                    )

                pdf_bytes = download_file(f"/api/export/{p['id']}/pdf")
                if pdf_bytes:
                    col_pdf.download_button(
                        "📕 PDF",
                        data=pdf_bytes,
                        file_name=f"proposal_{p['id'][:8]}.pdf",
                        mime="application/pdf",
                        key=f"pdf_{p['id']}",
                    )

                json_bytes = download_file(f"/api/export/{p['id']}/json")
                if json_bytes:
                    col_json.download_button(
                        "🗂️ JSON",
                        data=json_bytes,
                        file_name=f"proposal_{p['id'][:8]}.json",
                        mime="application/json",
                        key=f"json_{p['id']}",
                    )

            if col_del.button("🗑️ Delete", key=f"del_{p['id']}"):
                if api_delete(f"/api/proposals/{p['id']}"):
                    st.success("Deleted")
                    st.rerun()


# ── Page: Company Profiles ─────────────────────────────────────────────────────

def page_company():
    st.title("🏢 Company Profiles")
    st.markdown("Save your company details once. They'll be automatically injected into every proposal.")

    # List existing
    data = api_get("/api/profiles")
    profiles = data.get("items", []) if data else []

    if profiles:
        st.subheader("Saved Profiles")
        for p in profiles:
            star = " ⭐ Default" if p["is_default"] else ""
            with st.expander(f"**{p['company_name']}**{star} — `{p['id'][:8]}…`"):
                col1, col2 = st.columns(2)
                col1.write(f"**Tagline:** {p.get('tagline') or '—'}")
                col1.write(f"**Website:** {p.get('website') or '—'}")
                col1.write(f"**Email:** {p.get('contact_email') or '—'}")
                col2.write(f"**Services:** {p.get('services_offered') or '—'}")
                col2.write(f"**Team size:** {p.get('team_size') or '—'}")
                col2.write(f"**Years:** {p.get('years_in_business') or '—'}")

                col_def, col_del = st.columns([2, 1])
                if not p["is_default"]:
                    if col_def.button("⭐ Set as Default", key=f"def_{p['id']}"):
                        result = api_post(f"/api/profiles/{p['id']}/set-default", {})
                        if result:
                            st.success("Set as default!")
                            st.rerun()
                if col_del.button("🗑️ Delete", key=f"pdel_{p['id']}"):
                    if api_delete(f"/api/profiles/{p['id']}"):
                        st.success("Deleted")
                        st.rerun()

    st.divider()
    st.subheader("➕ Add New Profile")

    with st.form("profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            company_name = st.text_input("Company Name *", placeholder="Axiom Digital Agency")
            tagline = st.text_input("Tagline", placeholder="We build things that scale.")
            website = st.text_input("Website", placeholder="https://axiomdigital.io")
            contact_email = st.text_input("Contact Email", placeholder="hello@axiom.io")
            contact_phone = st.text_input("Contact Phone", placeholder="+1 (555) 000-1234")
        with col2:
            team_size = st.text_input("Team Size", placeholder="25–50")
            years = st.number_input("Years in Business", min_value=0, max_value=200, value=0)
            services = st.text_area("Services Offered", placeholder="Web dev, mobile apps, cloud…", height=80)
            industries = st.text_area("Industries Served", placeholder="FinTech, HealthTech, SaaS…", height=60)

        notable = st.text_input("Notable Clients", placeholder="Stripe, Shopify, Twilio")
        case_study = st.text_area("Case Study Summary", placeholder="Built X for Y, achieving Z…", height=80)
        is_default = st.checkbox("Set as default profile")

        if st.form_submit_button("💾 Save Profile", type="primary"):
            if not company_name.strip():
                st.error("Company Name is required")
            else:
                payload = {
                    "company_name": company_name.strip(),
                    "tagline": tagline or None,
                    "website": website or None,
                    "contact_email": contact_email or None,
                    "contact_phone": contact_phone or None,
                    "team_size": team_size or None,
                    "years_in_business": int(years) if years else None,
                    "services_offered": services or None,
                    "industries_served": industries or None,
                    "notable_clients": notable or None,
                    "case_study_summary": case_study or None,
                    "is_default": is_default,
                }
                result = api_post("/api/profiles", payload)
                if result:
                    st.success(f"✅ Profile '{result['company_name']}' saved!")
                    st.rerun()


# ── Page: Template Editor ──────────────────────────────────────────────────────

def page_templates():
    st.title("📝 Prompt Template Editor")
    st.markdown(
        "Edit the Jinja2 templates that instruct Claude how to write each section. "
        "Changes take effect immediately — no restart needed. "
        "Available variables: `{{ client_name }}`, `{{ project_description }}`, "
        "`{{ budget }}`, `{{ timeline }}`, `{{ goals }}`, `{{ tone_instructions }}`, `{{ company_profile }}`."
    )

    prompts_dir = Path("prompts")
    if not prompts_dir.exists():
        st.error("Prompts directory not found. Make sure you're running from the project root.")
        return

    template_files = {
        "system":             "system_prompt.j2",
        "executive_summary":  "executive_summary.j2",
        "technical_approach": "technical_approach.j2",
        "milestones":         "milestones.j2",
        "pricing_structure":  "pricing_structure.j2",
        "risks":              "risks.j2",
        "deliverables":       "deliverables.j2",
        "next_steps":         "next_steps.j2",
    }

    selected = st.selectbox(
        "Select template to edit",
        options=list(template_files.keys()),
        format_func=lambda k: SECTION_TEMPLATE_MAP.get(k, k),
    )

    template_path = prompts_dir / template_files[selected]
    if not template_path.exists():
        st.error(f"Template file not found: {template_path}")
        return

    current_source = template_path.read_text(encoding="utf-8")

    st.caption(f"📁 Editing: `{template_path}`")
    edited_source = st.text_area(
        "Template source",
        value=current_source,
        height=500,
        label_visibility="collapsed",
    )

    col_save, col_reset = st.columns([1, 5])
    if col_save.button("💾 Save", type="primary"):
        template_path.write_text(edited_source, encoding="utf-8")
        st.success(f"✅ Template `{template_files[selected]}` saved!")

    if col_reset.button("↩️ Reset to original"):
        st.info("To reset, restore the file from your git history: `git checkout prompts/`")

    with st.expander("Preview rendered output (with sample data)"):
        try:
            from backend.core.prompt_engine import PromptEngine
            engine = PromptEngine()
            ctx = engine.build_context(
                client_name="Acme Corp",
                project_description="Build a real-time analytics dashboard.",
                budget="$50,000",
                timeline="4 months",
                goals="Reduce reporting lag by 70%.",
                tone="professional",
            )
            if selected == "system":
                rendered = engine.render_system_prompt(ctx)
            else:
                rendered = engine.render_section(selected, ctx)
            st.code(rendered, language="markdown")
        except Exception as e:
            st.error(f"Render error: {e}")


# ── Page: About ────────────────────────────────────────────────────────────────

def page_about():
    st.title("ℹ️ About")

    # API health
    health = api_get("/health")
    if health:
        st.success(f"✅ Backend online — `{health['app']}` v{health['version']} ({health['environment']})")
    else:
        st.error("❌ Backend offline")

    st.markdown("""
## AI Proposal Generator

Convert raw client requirements into a polished, professional business proposal in under 2 minutes.

### How it works
1. **You** fill in the client name, project description, budget, timeline, and goals.
2. **The system** renders 8 specialised Jinja2 prompt templates and fires them to Claude in parallel.
3. **Claude** writes each section with the chosen tone (professional / friendly / technical / executive).
4. **You** get a complete proposal exported as Markdown, PDF, and JSON.

### Tech Stack
| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI + Uvicorn |
| LLM | Anthropic Claude (claude-sonnet-4) |
| Database | SQLite + SQLAlchemy |
| PDF export | WeasyPrint |
| Templates | Jinja2 |

### Future Improvements
- 🔗 Notion export integration
- 📧 Email delivery of proposals
- 🔐 Multi-user authentication
- 📊 Token usage analytics dashboard
- 🌐 Multi-language proposal support
- 🤖 Fine-tuned section regeneration with user feedback
- 📁 Template versioning and rollback
- 🔄 Webhook notifications on completion
    """)

    st.divider()
    st.caption("Built with FastAPI + Streamlit + Claude · MIT License")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="AI Proposal Generator",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS
    st.markdown("""
    <style>
        .stApp { max-width: 1200px; margin: 0 auto; }
        .metric-card { background: #f8f9fa; border-radius: 8px; padding: 12px; }
        div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 8px; }
        .stDownloadButton button { width: 100%; }
        div[data-testid="stForm"] { background: #fafafa; padding: 20px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

    # Sidebar navigation
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/document.png", width=60)
        st.title("Proposal Generator")
        st.caption("AI-powered · Claude-backed")
        st.divider()

        pages = {
            "✏️ Generate":  page_generate,
            "📋 History":   page_history,
            "🏢 Company":   page_company,
            "📝 Templates": page_templates,
            "ℹ️ About":     page_about,
        }

        # Honour programmatic page switches
        default_page = st.session_state.get("page", "✏️ Generate")
        if default_page not in pages:
            default_page = "✏️ Generate"
        default_idx = list(pages.keys()).index(default_page)

        selected_page = st.radio(
            "Navigation",
            list(pages.keys()),
            index=default_idx,
            label_visibility="collapsed",
        )
        st.session_state["page"] = selected_page

        st.divider()
        st.caption(f"API: `{API_BASE}`")

    # Render selected page
    pages[selected_page]()


if __name__ == "__main__":
    main()
