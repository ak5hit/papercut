import warnings
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change in a future version",
)

# 1. Import your working Qdrant client and setup from Phase 1
from ingest_and_search import client, COLLECTION_NAME, models

def get_context_string(query: str) -> str:
    """Helper function to execute the Hybrid Search and format the context."""
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=models.Document(text=query, model="BAAI/bge-small-en-v1.5"),
        using="fast-bge-small-en-v1.5",
        limit=3,
        with_payload=True
    ).points
    
    # Concatenate all the retrieved chunks into one massive text block
    context = "\n\n".join([
        f"Source Data:\n{point.payload.get('document', '') if point.payload else ''}"
        for point in results
    ])
    return context

# ==========================================
# 2. Define the Shared Memory State
# ==========================================
class AgentState(TypedDict):
    question: str
    context: str
    answer: str
    revision_count: int
    critique: str

# ==========================================
# 3. Define the Nodes (The Agents)
# ==========================================
def researcher_node(state: AgentState):
    """Agent 1: The Data Fetcher. Queries the Vector DB."""
    question = state["question"]
    print(f"\n[Researcher] Querying local Qdrant database for: '{question}'...")
    
    context = get_context_string(question)
    
    print("[Researcher] Found relevant context. Passing payload to Analyst.")
    return {"context": context}


def analyst_node(state: AgentState):
    """Agent 2: The Reasoning Engine. Synthesizes data via local LLM."""
    question = state["question"]
    context = state["context"]
    critique = state.get("critique", "")
    revision_count = state.get("revision_count", 0) + 1

    print(f"[Analyst] Running revision #{revision_count}...")
    if critique:
        print(f"[Analyst] Previous critique: {critique}")
    print("[Analyst] Reading context and spinning up local Llama 3 model...")

    llm = ChatOllama(model="llama3", temperature=0.5)

    prompt_text = (
        "You are a Lead Medical AI. Answer the user's question using ONLY the provided context. "
        "If the answer is not in the context, explicitly state 'Insufficient data in the knowledge base.'\n\n"
    )

    if critique:
        prompt_text += (
            f"Your previous answer was rejected for this reason: {critique}. "
            "Rewrite it to be strictly factual.\n\n"
        )

    prompt_text += (
        "CONTEXT:\n{context}\n\n"
        "QUESTION:\n{question}"
    )

    prompt = ChatPromptTemplate.from_template(prompt_text)
    chain = prompt | llm
    response = chain.invoke({"question": question, "context": context})

    print(f"[Analyst] Completed revision #{revision_count}.")
    return {"answer": response.content, "revision_count": revision_count}


def critic_node(state: AgentState):
    """Agent 3: The Critic. Validates the Analyst's answer against the context."""
    answer = state["answer"]
    context = state["context"]

    print("[Critic] Evaluating analyst answer for hallucinations...")

    llm = ChatOllama(model="llama3", temperature=0)
    prompt = ChatPromptTemplate.from_template(
        "Review the following answer and context. "
        "If the answer is fully supported by the context, output exactly 'PASS'. "
        "If the answer contains hallucinations, unsupported claims, or outside knowledge, output exactly 'FAIL: [Reason]'.\n\n"
        "CONTEXT:\n{context}\n\n"
        "ANSWER:\n{answer}"
    )

    chain = prompt | llm
    response = chain.invoke({"context": context, "answer": answer})
    result = response.content.strip()

    critique = ""
    if result.upper().startswith("PASS"):
        print("[Critic] PASS — answer is supported by the context.")
    elif result.upper().startswith("FAIL"):
        critique = result.split(":", 1)[1].strip() if ":" in result else result
        print(f"[Critic] FAIL — hallucination detected: {critique}")
    else:
        critique = f"Unclear critic response: {result}"
        print(f"[Critic] FAIL — unexpected critic output: {result}")

    return {"critique": critique}

# ==========================================
# 4. Build and Compile the Graph (The State Machine)
# ==========================================
workflow = StateGraph(AgentState)

workflow.add_node("researcher", researcher_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("critic", critic_node)

workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "analyst")
workflow.add_edge("analyst", "critic")


def route_after_critic(state: AgentState):
    critique = state.get("critique", "")
    revision_count = state.get("revision_count", 0)

    if not critique:
        print("[Router] Critic passed — ending workflow.")
        return "END"

    if revision_count >= 3:
        print(f"[Router] Revision limit reached ({revision_count}) — ending workflow.")
        return "END"

    print(f"[Router] Hallucination caught. Routing back to analyst for revision #{revision_count + 1}.")
    return "analyst"

workflow.add_conditional_edges("critic", route_after_critic, {"analyst": "analyst", "END": END})

app = workflow.compile()

# ==========================================
# 5. Execution Block
# ==========================================
if __name__ == "__main__":
    print("\n==========================================")
    print("STARTING LOCAL MULTI-AGENT PIPELINE (interactive)")
    print("==========================================")

    try:
        while True:
            try:
                question = input("\nEnter question (or type 'exit' to quit): ").strip()
            except EOFError:
                print("\nEOF received, exiting.")
                break

            if not question:
                continue
            if question.lower() in ("exit", "quit"):
                print("Exiting.")
                break

            initial_state = {
                "question": question,
                "context": "",
                "answer": "",
                "revision_count": 0,
                "critique": ""
            }

            final_state = app.invoke(initial_state)

            print("\n------------------------------------------")
            print("Answer:")
            print("------------------------------------------")
            print(final_state.get("answer", "(no answer returned)"))
            print("------------------------------------------")

    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")