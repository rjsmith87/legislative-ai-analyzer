# Legislative AI Analyzer

**AI-powered pipeline that reads Texas legislative bills, extracts fiscal impacts with Claude AI, and delivers structured analysis through Salesforce Agentforce — deployed on Heroku with Redis caching and background job processing.**

---

## The Problem

Texas publishes hundreds of bills per legislative session, each with complex fiscal notes buried in dense PDFs. Legislative analysts, lobbyists, and government affairs teams spend hours manually reading and summarizing these documents. The fiscal data is unstructured, making it difficult to compare bills or track cumulative budget impact.

## The Solution

This project automates the entire legislative analysis workflow:

1. **Fetches** bill text and fiscal notes directly from the Texas Legislature (Telicon)
2. **Extracts** full text from PDFs using pdfminer
3. **Analyzes** content with Claude AI via Heroku Managed Inference
4. **Calculates** five-year fiscal impact totals from unstructured fiscal notes
5. **Returns** both natural language summaries and structured data to Salesforce Agentforce
6. **Caches** results in Redis (45%+ hit rate) to minimize redundant AI calls
7. **Handles** large bills (500+ pages) via background worker jobs

---

## Tech Stack

| Layer | Technology | Purpose |
|:------|:-----------|:--------|
| **AI/LLM** | Claude AI (Heroku Managed Inference) | Bill summarization and fiscal data extraction |
| **Web Framework** | Flask + Gunicorn | REST API serving analysis endpoints |
| **PDF Processing** | pdfminer.six | Text extraction from legislative PDFs |
| **Caching** | Redis | Result caching with configurable TTL |
| **Background Jobs** | RQ (Redis Queue) | Async processing for large bills |
| **AI Orchestration** | Salesforce Agentforce | Conversational interface for bill queries |
| **External Service** | Salesforce External Services (OpenAPI) | API integration layer |
| **Backend Logic** | Apex (BillSummarizerInvocable) | Salesforce-side invocable actions |
| **Data Source** | Texas Legislature / Telicon | Bill text and fiscal note PDFs |
| **Hosting** | Heroku (Python 3.11) | Web + Worker dyno deployment |

---

## Architecture

```
  User Query                    HEROKU PLATFORM
  "Analyze HB 150"       ┌──────────────────────────────────┐
        │                 │                                  │
        ▼                 │   ┌─────────────┐                │
  ┌───────────┐           │   │  Flask API  │                │
  │ Agentforce│           │   │  /analyze   │                │
  │   Agent   │──────────▶│   │  BillFor    │                │
  │           │           │   │  Agentforce │                │
  └───────────┘           │   └──────┬──────┘                │
        ▲                 │          │                       │
        │                 │    ┌─────▼──────┐   ┌─────────┐ │
        │                 │    │ Redis Cache │   │ RQ      │ │
        │                 │    │ (hit? skip) │   │ Worker  │ │
        │                 │    └─────┬──────┘   │ (large  │ │
        │                 │          │ miss      │  bills) │ │
        │                 │    ┌─────▼──────┐   └────┬────┘ │
        │                 │    │  Fetch PDF  │◀───────┘      │
        │                 │    │  from Texas │               │
        │                 │    │  Legislature│               │
        │                 │    └─────┬──────┘               │
        │                 │          │                       │
        │                 │    ┌─────▼──────┐               │
        │                 │    │  pdfminer   │               │
        │                 │    │  Extract    │               │
        │                 │    │  Text       │               │
        │                 │    └─────┬──────┘               │
        │                 │          │                       │
        │                 │    ┌─────▼──────┐               │
        │                 │    │  Claude AI  │               │
        │                 │    │  Summarize  │               │
        │                 │    │  + Extract  │               │
        │                 │    │  Fiscal $   │               │
        │                 │    └─────┬──────┘               │
        │                 │          │                       │
        │                 └──────────┼───────────────────────┘
        │                            │
        └────────────────────────────┘
              Structured response:
              summary, fiscal impact,
              five-year total, URLs

  ┌──────────────────────────────────────────────────────┐
  │  Salesforce Org                                      │
  │  ┌──────────────┐  ┌──────────────┐                  │
  │  │ Legislation  │  │ Bill         │                  │
  │  │ __c          │──│ Analysis__c  │                  │
  │  │ (parent)     │  │ (child)      │                  │
  │  └──────────────┘  └──────────────┘                  │
  └──────────────────────────────────────────────────────┘
```

---

## How It Works

1. **Query** — A user asks the Agentforce agent to analyze a bill (e.g., "Analyze HB 150")
2. **Cache Check** — Redis is checked for a cached result (45%+ hit rate)
3. **Fetch** — On cache miss, the bill PDF and fiscal note are fetched from the Texas Legislature via Telicon
4. **Extract** — pdfminer extracts text from the PDFs, with smart truncation for Claude's context window
5. **Analyze** — Claude AI generates a structured summary and extracts fiscal impact data, including line-item parsing and five-year totals
6. **Cache** — Results are cached in Redis with configurable TTL
7. **Respond** — Agentforce receives a formatted natural language response plus structured data for Salesforce record creation
8. **Large Bills** — Bills over 500 pages are routed to a background RQ worker to avoid request timeouts

---

## API Endpoints

| Endpoint | Method | Description |
|:---------|:-------|:------------|
| `/health` | GET | System status and dependency health |
| `/analyzeBillForAgentforce` | POST | Agentforce-optimized endpoint (returns formatted text) |
| `/analyzeBill` | POST | Full analysis (returns structured JSON) |
| `/cache/stats` | GET | Redis cache performance metrics |
| `/cache/invalidate` | POST | Clear cache for a specific bill |
| `/job/<job_id>` | GET | Check background job status |

---

## Repository Structure

```
legislative-ai-analyzer/
├── app.py                          # Flask API — bill fetching, analysis, caching
├── tasks.py                        # RQ background worker tasks for large bills
├── worker.py                       # RQ worker process entry point
├── requirements.txt                # Python dependencies
├── runtime.txt                     # Python version for Heroku
├── Procfile                        # Heroku process definitions (web + worker)
├── app.json                        # Heroku one-click deploy manifest
├── BillSummarizerProject/          # Salesforce SFDX project
│   └── force-app/main/default/
│       └── classes/                # Apex invocable actions
├── BillSummarizerInvocable.cls.rtf # Apex class reference
├── SETUP_GUIDE.md                  # Salesforce configuration walkthrough
└── DEPLOYMENT_CHECKLIST.md         # Pre-deployment verification steps
```

---

## Setup

### Prerequisites
- Python 3.11+
- Heroku CLI with Managed Inference access
- Salesforce org with Agentforce enabled

### One-Click Deploy

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rjsmith87/legislative-ai-analyzer)

This provisions:
- Web + Worker dynos ($7/month each)
- Redis Mini ($15/month) for caching
- Claude AI via Heroku Managed Inference (~$0.30/1M tokens)

### Local Development
```bash
pip install -r requirements.txt
export INFERENCE_URL=<your-heroku-inference-url>
export INFERENCE_KEY=<your-heroku-inference-key>
export REDIS_URL=<your-redis-url>
python app.py
```

### Salesforce Configuration
See [SETUP_GUIDE.md](SETUP_GUIDE.md) for step-by-step instructions on configuring External Services, custom objects, and the Agentforce agent.

---

## Cost

| Component | Cost | Notes |
|:----------|:-----|:------|
| Eco Dynos (2) | $14/mo | Web + Worker |
| Redis Mini | $15/mo | Caching layer |
| Heroku Inference | ~$20-50/mo | Usage-based Claude API |
| **Total** | **$49-79/mo** | Per instance |

---

## Contributing

Found a bug? Want to add support for another state?

1. Fork this repo
2. Create a feature branch
3. Submit a pull request

[Open an issue](https://github.com/rjsmith87/legislative-ai-analyzer/issues) for questions or feature requests.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
