# Clean Project Structure — AcademeRAG-Final

The following is the cleaned and consolidated layout of the AcademeRAG-Final codebase:

```text
AcademeRAG-Final/
├── .github/
│   └── workflows/
│       ├── ci.yml                     # Continuous integration pipeline
│       └── security-supply-chain.yml   # Gitleaks, pip-audit, and dependency check workflow
├── api/                                # Core Django REST application
│   ├── migrations/                    # Relational database schema migrations
│   ├── admin.py
│   ├── apps.py
│   ├── auth_utils.py                  # JWT authorization decorators and helpers
│   ├── auth_views.py                  # User authentication (register, login, refresh)
│   ├── error_views.py
│   ├── logging_filters.py
│   ├── logging_formatters.py
│   ├── metrics.py                     # Prometheus custom telemetry counters/histograms
│   ├── middleware.py                  # Metrics and request trace ID middlewares
│   ├── models.py                      # Database models (IndexedDocument)
│   ├── rate_limit.py                  # Redis-backed fail-closed rate limiter
│   ├── request_context.py
│   ├── responses.py
│   ├── settings.py
│   ├── urls.py                        # App route maps (/api/auth/*, /api/ask/*, /api/health/*)
│   └── views.py                       # Ask (QA), stream, diagnostics, and health check handlers
├── documents/                          # Source academic PDF corpus
│   ├── RAG sample 1.pdf
│   └── RAG sample 2.pdf
├── docs/
│   └── openapi.yaml                   # OpenAPI API endpoints spec
├── eval/                               # Evaluation framework
│   ├── golden_set_academic.json       # Factual, syllabus, and neg-test QA benchmarks
│   ├── golden_set.json                # Synthetic validation cases
│   ├── latest_report.json
│   ├── load_test.py                   # Locust load testing simulator
│   ├── thresholds.json                # Quality gate metric limits
│   └── rag_eval.py                    # RAG LLM-as-a-judge regression evaluation harness
├── Frontend/                           # React + Vite + TypeScript client
│   ├── public/                        # Static web assets
│   ├── src/                           # Source files
│   │   ├── components/                # UI and protected routing components
│   │   ├── hooks/
│   │   ├── lib/                       # API client, feature flags, telemetry, sanitizers
│   │   ├── pages/                     # Views (AuthPage, ChatPage, NotFound)
│   │   ├── store/                     # Zustand chat state store (chat-store.ts)
│   │   ├── App.tsx                    # React client route definitions
│   │   └── main.tsx                   # React client entry point
│   ├── tests/                         # E2E and unit test directories
│   ├── playwright.config.ts           # Playwright configuration
│   ├── tailwind.config.ts             # Tailwind CSS tokens and themes
│   ├── vite.config.ts                 # Vite bundler options
│   ├── vitest.config.ts               # Vitest runner settings
│   └── package.json                   # Frontend script definitions and node dependencies
├── rag/                                # Core LLM & Ingestion orchestration package
│   ├── __init__.py
│   ├── llm_orchestration.py           # LLM Groq online / Ollama offline failover router
│   ├── pdf_sandbox.py                 # Multi-processed isolated safe PDF reader
│   └── scoring.py                     # Algorithmic RAG pipeline pipeline evaluation
├── rag_project/                        # Django project configuration
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py                    # Global settings (CORS, JWT, logging, Postgres/SQLite CACHES)
│   ├── urls.py                        # Main Django route dispatcher
│   └── wsgi.py
├── static/                             # Static files collection directory
├── .coveragerc                         # Test coverage options
├── .env                                # Local environment parameters (excluded from Git)
├── .gitignore                          # Git patterns exclude rules
├── AGENTS.md                           # Repository coding style guidelines
├── ARCHITECTURE_DIAGRAMS.md            # RAG flow topology and architecture maps
├── Consequences.txt                    # Development obstacles log
├── Dockerfile.backend                  # Django container definition
├── Dockerfile.frontend                 # React/Vite web server container definition
├── docker-compose.prod.yml             # Local production services composer configuration
├── main.py                             # Unified startup entry point and system checks launcher
├── manage.py                           # Django CLI utility
├── Milvus.py                           # Dense/sparse vector retrieval core engine
├── requirements.txt                    # Main deploy requirements route
├── requirements_django.txt             # Primary Django and Python dependencies list
└── README.md                           # General documentation, commands, and guide
```
