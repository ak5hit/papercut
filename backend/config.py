from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/doc_intelligence"
    host: str = "0.0.0.0"
    port: int = 8000

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://localhost:11434"

    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    retrieval_min_similarity: float = 0.5

    # Graph extraction
    graph_extraction_enabled: bool = True
    graph_chunks_to_combine: int = 3
    graph_strong_entity_types: str = "Organization,Location,Date,Money,Event,Document,Concept,Skill,Profession"
    graph_allowed_nodes: str = ""
    graph_allowed_relationships: str = ""
    graph_max_traversal_depth: int = 2
    age_database_url: str = "postgresql+asyncpg://postgres:postgres@age:5432/doc_graph"
    graph_entity_dedup_threshold: float = 0.95
    graph_auto_postprocess: bool = True
    graph_auto_consolidate_labels: bool = True
    graph_auto_merge_duplicates: bool = False
    graph_batch_size: int = 20
    chunk_token_size: int = 512
    chunk_token_overlap: int = 50

    chat_session_ttl_hours: int = 24

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def strong_entity_types_list(self) -> list[str]:
        return [t.strip() for t in self.graph_strong_entity_types.split(",") if t.strip()]


settings = Settings()
