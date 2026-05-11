# 📄 AI Proposal Generator

> Convert raw client requirements into a polished, professional business proposal automatically, in under 2 minutes.

Built with **FastAPI** · **Claude (Anthropic)** · **Streamlit** · **SQLite** · **WeasyPrint**

---

## ✨ Features

| Feature | Details |
|---|---|
| 🤖 AI-powered generation | 8 specialised sections written in parallel by Claude |
| 🎨 Tone selector | Professional · Friendly · Technical · Executive |
| 📦 Triple export | Markdown · PDF · JSON metadata |
| 🏢 Company memory | Save your agency profile once, inject into every proposal |
| 📝 Template editor | Edit Jinja2 prompts live in the UI — no restart needed |
| 🔄 Section regeneration | Re-generate individual sections on demand |
| 🗃️ Proposal history | Browse, re-download, and delete past proposals |
| 📊 Structured logging | JSON logs in production, coloured text in development |

---

## 🗂️ Project Structure

```
proposal-generator/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Pydantic Settings (.env loader)
│   ├── logger.py                  # Structured JSON/text logger
│   ├── middleware.py              # Request ID + timing middleware
│   ├── api/
│   │   ├── routes_proposals.py    # POST /generate, GET/DELETE proposals
│   │   ├── routes_export.py       # Download MD/PDF/JSON
│   │   └── routes_profiles.py     # Company profile CRUD
│   ├── core/
│   │   ├── prompt_engine.py       # Jinja2 template loader & renderer
│   │   ├── llm_client.py          # Async Claude API wrapper + retry
│   │   ├── proposal_builder.py    # 8-section orchestrator
│   │   └── export_service.py      # MD → PDF → JSON pipeline
│   ├── db/
│   │   ├── database.py            # SQLAlchemy engine + session
│   │   ├── models.py              # Proposal + CompanyProfile ORM models
│   │   └── crud.py                # DB helper functions
│   └── schemas/
│       ├── proposal.py            # Pydantic request/response schemas
│       └── profile.py
├── frontend/
│   └── app.py                     # Streamlit UI
├── prompts/                       # Editable Jinja2 templates
│   ├── system_prompt.j2
│   ├── executive_summary.j2
│   ├── technical_approach.j2
│   ├── milestones.j2
│   ├── pricing_structure.j2
│   ├── risks.j2
│   ├── deliverables.j2
│   └── next_steps.j2
├── generated/                     # Runtime output (git-ignored)
├── logs/                          # Rotating log files (git-ignored)
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/yourorg/proposal-generator.git
cd proposal-generator

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set your Anthropic API key:

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

### 3. Start the backend

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Visit **http://localhost:8000/docs** to explore the interactive API.

### 4. Start the frontend

Open a second terminal:

```bash
streamlit run frontend/app.py
```

Visit **http://localhost:8501** to use the UI.

---

## 🔧 Configuration Reference

All settings are loaded from `.env` (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic secret key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `ANTHROPIC_MAX_TOKENS` | `4096` | Max tokens per section |
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `DATABASE_URL` | `sqlite:///./proposal_generator.db` | SQLAlchemy connection string |
| `DEFAULT_TONE` | `professional` | Default proposal tone |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FORMAT` | `json` | `json` (production) or `text` (dev) |
| `GENERATION_TIMEOUT_SECONDS` | `120` | Max wait for generation |

---

## 📡 API Reference

### Proposals

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/proposals/generate` | Submit new proposal (async) |
| `GET` | `/api/proposals` | List all proposals |
| `GET` | `/api/proposals/{id}` | Get single proposal + all sections |
| `DELETE` | `/api/proposals/{id}` | Delete proposal |
| `POST` | `/api/proposals/{id}/regenerate?section=X` | Re-generate one section |

### Export

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/export/{id}/markdown` | Download `.md` file |
| `GET` | `/api/export/{id}/pdf` | Download `.pdf` file |
| `GET` | `/api/export/{id}/json` | Download `.json` metadata |
| `GET` | `/api/export/{id}/status` | Check which formats are ready |

### Company Profiles

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/profiles` | Create profile |
| `GET` | `/api/profiles` | List all profiles |
| `GET` | `/api/profiles/default` | Get default profile |
| `GET` | `/api/profiles/{id}` | Get single profile |
| `PATCH` | `/api/profiles/{id}` | Partial update |
| `DELETE` | `/api/profiles/{id}` | Delete profile |
| `POST` | `/api/profiles/{id}/set-default` | Mark as default |

### Example — Generate a proposal

```bash
curl -X POST http://localhost:8000/api/proposals/generate \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Acme Corporation",
    "project_description": "Build a real-time logistics dashboard with live shipment tracking and automated reporting.",
    "budget": "$50,000 – $70,000",
    "timeline": "5 months",
    "goals": "Reduce manual reporting by 70%, give managers live shipment visibility, mobile-first design.",
    "tone": "professional"
  }'
```

Response (202 Accepted):
```json
{
  "proposal_id": "a1b2c3d4-...",
  "status": "pending",
  "message": "Proposal generation started. Poll GET /api/proposals/{id} for status."
}
```

---

## 🎨 Prompt Template Variables

All templates are in `/prompts/*.j2` and use Jinja2 syntax.

| Variable | Type | Description |
|---|---|---|
| `{{ client_name }}` | `str` | Client organisation name |
| `{{ project_description }}` | `str` | Full project description |
| `{{ budget }}` | `str` | Budget range or amount |
| `{{ timeline }}` | `str` | Project duration |
| `{{ goals }}` | `str` | Business goals and KPIs |
| `{{ tone }}` | `str` | Tone key (e.g. `professional`) |
| `{{ tone_instructions }}` | `str` | Resolved tone description for Claude |
| `{{ company_profile }}` | `object\|None` | Company profile (fields: `.company_name`, `.tagline`, `.services_offered`, etc.) |

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

---

## 🔮 Future Improvements

| Priority | Feature | Description |
|---|---|---|
| 🔴 High | **Notion export** | One-click push proposal to a Notion page via API |
| 🔴 High | **Authentication** | JWT-based multi-user support with per-user proposal isolation |
| 🟡 Medium | **Email delivery** | Send finished proposals via SendGrid or Resend |
| 🟡 Medium | **Streaming generation** | SSE stream section content as it's generated (no polling) |
| 🟡 Medium | **Template versioning** | Git-backed template history with rollback |
| 🟡 Medium | **Token analytics** | Dashboard showing cost-per-proposal and model usage |
| 🟢 Low | **Multi-language** | Generate proposals in French, German, Spanish, etc. |
| 🟢 Low | **Feedback loop** | Thumbs up/down per section to improve future prompts |
| 🟢 Low | **Proposal comparison** | Side-by-side diff of two versions of the same proposal |
| 🟢 Low | **CRM integration** | Push proposals to HubSpot / Pipedrive deals |
| 🟢 Low | **Custom branding** | Upload logo → injected into PDF header |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│         Streamlit Frontend              │
│  Input form · Preview · Export panel    │
└──────────────┬──────────────────────────┘
               │ HTTP/REST
┌──────────────▼──────────────────────────┐
│         FastAPI Backend                 │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐  │
│  │ Proposal │ │  Export  │ │Profile  │  │
│  │  Routes  │ │  Routes  │ │ Routes  │  │
│  └────┬─────┘ └────┬─────┘ └────┬────┘  │
│       │            │            │       │
│  ┌────▼────────────▼────────────▼────┐  │
│  │           Core Engine             │  │
│  │  PromptEngine · LLMClient         │  │
│  │  ProposalBuilder · ExportService  │  │
│  └───────────────────────────────────┘  │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│         Persistence Layer               │
│  SQLite DB · /generated · /prompts      │
└─────────────────────────────────────────┘
```

---

## 📄 License

MIT — use freely, attribution appreciated.
