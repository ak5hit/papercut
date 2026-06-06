import pandas as pd
from datasets import Dataset
from ragas import evaluate
# FIX 1: Import the pre-initialized metric objects directly
from ragas.metrics import faithfulness, context_precision 
from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

# Import your compiled LangGraph app from Phase 2/3
from agent_graph import app 

def run_evaluation():
    print("\n==========================================")
    print("STARTING LLMOPS EVALUATION PIPELINE")
    print("==========================================\n")

    # 1. Your Ground Truth Test Dataset
    questions = [
        "What are the characteristics of an attenuated virus?",
        "What are the two main types of currently licensed vaccines mentioned?"
    ]
    
    ground_truths = [
        "An attenuated virus is one that is genetically disabled or killed to prevent replication.",
        "Most currently licensed vaccines are either subunit vaccines or attenuated forms of disease-causing microorganisms."
    ]

    data_for_ragas = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": ground_truths
    }

    # 2. Run the test questions through your multi-agent system
    for q in questions:
        print(f"Testing pipeline with query: '{q}'...")
        
        # FIX 2: Ensure revision_count is initialized to prevent graph KeyError
        state = {"question": q, "context": "", "answer": "", "revision_count": 0}
        result = app.invoke(state)
        
        data_for_ragas["question"].append(q)
        data_for_ragas["answer"].append(result.get("answer", ""))
        
        raw_context = result.get("context", "")
        context_list = [c.strip() for c in raw_context.split("Source Data:\n") if c.strip()]
        data_for_ragas["contexts"].append(context_list)

    # 3. Convert to HuggingFace Dataset
    dataset = Dataset.from_dict(data_for_ragas)

    # 4. Define the Evaluator Models (The "Judges")
    print("\nSpinning up local LLM-as-a-Judge (Llama 3)...")
    
    # FIX 3: Use the standard LangChain ChatOllama wrapper
    judge_llm = ChatOllama(model="llama3", temperature=0)
    judge_embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")

    # 5. Execute Ragas Evaluation
    print("Running Ragas Metrics (Faithfulness & Context Precision)...")
    print("This may take a minute depending on your local hardware.")
    
    # FIX 4: Pass the pre-initialized metrics to the evaluate function
    eval_result = evaluate(
        dataset,
        metrics=[faithfulness, context_precision],
        llm=judge_llm,
        embeddings=judge_embeddings
    )

    # 6. Output and Save Results
    print("\n==========================================")
    print("EVALUATION SCORES (0.0 to 1.0):")
    print("==========================================")
    print(eval_result)
    
    df = eval_result.to_pandas()
    df.to_csv("ragas_evaluation_results.csv", index=False)
    print("\nSaved detailed node-by-node breakdown to 'ragas_evaluation_results.csv'")

if __name__ == "__main__":
    run_evaluation()