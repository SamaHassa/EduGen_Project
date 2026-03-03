# retriever.py
import os
import numpy as np
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# CONFIG
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# HELPER FUNCTIONS

def cosine_similarity(vec1, vec2):
    """Compute cosine similarity between two vectors"""
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

def parse_embedding(embedding_str):
    """Convert string representation of list to numpy float array"""
    if isinstance(embedding_str, str):
        # remove brackets and split
        emb_list = embedding_str.strip('[]').split(',')
        emb_floats = [float(x) for x in emb_list]
        return np.array(emb_floats, dtype=float)
    elif isinstance(embedding_str, list):
        return np.array(embedding_str, dtype=float)
    else:
        raise ValueError("Unknown embedding format")


# MAIN RETRIEVAL

def retrieve(query, top_k=5, similarity_threshold=0.2):
    """
    Retrieve top_k most relevant chunks for the query
    similarity_threshold: low by default (0.2) to avoid top 0 results
    """
    # 1. Embed the query
    from langchain_huggingface import HuggingFaceEmbeddings
    embeddings_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    query_vector = embeddings_model.embed_query(query)

    # 2. Load all chunks from Supabase
    response = supabase.table("pdf_chunks").select("*").execute()
    chunks = response.data

    # 3. Compute similarity
    similarities = []
    for chunk in chunks:
        try:
            chunk_vector = parse_embedding(chunk["embedding"])
        except Exception as e:
            print(f"Skipping chunk {chunk['pdf_name']} index {chunk['chunk_index']} due to embedding error: {e}")
            continue
        score = cosine_similarity(query_vector, chunk_vector)
        similarities.append((score, chunk))

    # 4. Sort by similarity descending
    similarities.sort(key=lambda x: x[0], reverse=True)

    # 5. Deduplicate text
    top_chunks = []
    seen_texts = set()
    for score, chunk in similarities:
        text = chunk["content"]
        if text not in seen_texts and score >= similarity_threshold:
            top_chunks.append(chunk)
            seen_texts.add(text)
        if len(top_chunks) >= top_k:
            break

    return top_chunks


# TEST / RUN

if __name__ == "__main__":
    query = "Explain supervised learning"
    top_chunks = retrieve(query, top_k=5, similarity_threshold=0.2)
    print(f"Top {len(top_chunks)} chunks for query: '{query}'\n")
    for i, chunk in enumerate(top_chunks, start=1):
        print(f"Chunk {i} from {chunk['pdf_name']} (index {chunk['chunk_index']}):")
        print(chunk["content"][:500], "\n")