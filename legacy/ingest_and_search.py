import os
import warnings

# Suppress urllib3 warnings
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL')

from qdrant_client import QdrantClient, models
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

# 1. Initialize Qdrant Client 
# (Using local memory for testing; change to URL/Port when you spin up Docker)
client = QdrantClient(":memory:")

COLLECTION_NAME = "diagnostic_knowledge_base"

# 2. Setup the Collection with Hybrid Search capabilities
# We use FastEmbed to handle the vectorization locally.
client.set_model("BAAI/bge-small-en-v1.5") # Dense model (Semantic meaning)
client.set_sparse_model("prithivida/Splade_PP_en_v1") # Sparse model (Exact keywords)

# Recreate the collection to ensure a clean slate
if client.collection_exists(COLLECTION_NAME):
    client.delete_collection(COLLECTION_NAME)

client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=client.get_fastembed_vector_params(),
    sparse_vectors_config=client.get_fastembed_sparse_vector_params(),
)

def process_and_ingest_document(pdf_path: str):
    print(f"Loading and chunking document: {pdf_path}...")
    
    # 3. Intelligent Chunking
    # We use Recursive splitters to respect paragraph and sentence boundaries
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = text_splitter.split_documents(docs)
    
    # Extract text content and metadata
    documents = [chunk.page_content for chunk in chunks]
    metadata = [{"source": chunk.metadata["source"], "page": chunk.metadata["page"]} for chunk in chunks]
    
    print(f"Generated {len(documents)} semantic chunks. Ingesting to Qdrant...")
    
    # 4. Add to Qdrant (FastEmbed automatically handles the dense + sparse vectorization here)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=UserWarning, message='.*add.*method has been deprecated.*')
        client.add(
            collection_name=COLLECTION_NAME,
            documents=documents,
            metadata=metadata,
            parallel=4  # Multithreading for faster local processing
        )
    print("Ingestion complete.\n")

def hybrid_search(query: str, limit: int = 3):
    print(f"Executing Hybrid Search for: '{query}'")
    
    # 5. The Query Execution
    # Qdrant's Query API automatically handles fusing the dense and sparse scores
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=UserWarning, message='.*query.*method has been deprecated.*')
        results = client.query(
            collection_name=COLLECTION_NAME,
            query_text=query,
            limit=limit
        )
    
    for i, point in enumerate(results):
        print(f"\n--- Result {i+1} (Score: {point.score:.4f}) ---")
        print(f"Source: Page {point.metadata.get('page')} of {point.metadata.get('source')}")
        print(f"Text: {point.document}")

# ==========================================
# Execution Block
# ==========================================
if __name__ == "__main__":
    sample_pdf = "sample_technical_document.pdf" 
    
    # Create a dummy file just so the script doesn't crash if you run it immediately
    if not os.path.exists(sample_pdf):
        print("Please place a PDF named 'sample_technical_document.pdf' in the directory.")
    else:
        process_and_ingest_document(sample_pdf)
        
        # Test a query. Notice how you can ask for both semantic meaning and exact keywords.
        test_query = "What are some known viruses?"
        hybrid_search(test_query)