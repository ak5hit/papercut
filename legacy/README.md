# Legacy Code

These files are from the original hybrid RAG implementation that served as the foundation for this project. They have been superseded by the modern architecture and are kept for reference only — none of them are imported or used by the current application.

## What was replaced

| Legacy File | Purpose | Superseded By |
|---|---|---|
| `ingest_and_search.py` | Qdrant in-memory document ingestion + hybrid retrieval | `backend/storage/` + PostgreSQL/pgvector |
| `agent_graph.py` | LangGraph multi-agent query pipeline with hallucination checking | `backend/query/planner.py` + `backend/answers/composer.py` |
| `eval_pipeline.py` | RAGAS evaluation pipeline (faithfulness, context precision) | `backend/evaluation/harness.py` |
| `requirements.txt` | Dependencies for the legacy pipeline (qdrant-client, langchain, langgraph, litellm, etc.) | `backend/requirements.txt` |
| `ragas_evaluation_results.csv` | Output artifact from `eval_pipeline.py` | — |

## Architecture Evolution

The original system used:
- **Qdrant** for in-memory vector storage → replaced with **PostgreSQL + pgvector**
- **LangGraph** for multi-agent orchestration → replaced with **QueryPlanner + AnswerComposer**
- **Direct model imports** (ChatOllama, LangChain) → replaced with **LLM provider abstraction** (`backend/llm/`)
- **Ad-hoc scripts** → replaced with **FastAPI application + proper module structure**
