# edugen/models/exam_generator.py

import sys
import os
import re
from supabase import create_client, Client

# Ensure project root (edugen/) is on sys.path so sibling packages import correctly
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from rag.retriever import retrieve
from llm.llama_client import generate_from_llm
import json
from datetime import datetime, timezone


# Supabase config
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# Helper: extract JSON from LLM response

def extract_json(text: str):
    """
    Extract a JSON array from LLM output that may contain markdown fences
    or surrounding text.
    """
    # Try to strip markdown code fences (```json ... ``` or ``` ... ```)
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1)

    # Find the first '[' and last ']' to isolate the JSON array
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return json.loads(text)


# Dummy fallback for mixed-type exams

def _dummy_mixed(mcq_count: int, tf_count: int, essay_count: int) -> list:
    questions = []
    for i in range(mcq_count):
        questions.append({
            "type": "mcq",
            "question": f"MCQ placeholder question {i + 1}",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "answer": "A",
        })
    for i in range(tf_count):
        questions.append({
            "type": "tf",
            "question": f"True/False placeholder question {i + 1}",
            "answer": "True",
        })
    for i in range(essay_count):
        questions.append({
            "type": "essay",
            "question": f"Essay placeholder question {i + 1}",
            "answer": "Key points: provide a detailed explanation.",
        })
    return questions


# Generate Exam Function

def generate_exam(
    subject: str,
    topic: str = None,
    num_questions: int = 5,
    difficulty: str = "Beginner",
    context_text: str = None,
    mcq_count: int = None,
    tf_count: int = None,
    essay_count: int = None,
):
    """
    Generate a mixed-type exam (MCQ, True/False, Essay).
    If mcq_count/tf_count/essay_count are given they override num_questions.
    If context_text is supplied the RAG retriever is skipped.
    """
    # Resolve counts
    if mcq_count is None and tf_count is None and essay_count is None:
        # Default: split num_questions into roughly equal thirds
        mcq_count   = max(1, round(num_questions * 0.5))
        tf_count    = max(1, round(num_questions * 0.25))
        essay_count = max(1, num_questions - mcq_count - tf_count)
    else:
        mcq_count   = mcq_count   or 0
        tf_count    = tf_count    or 0
        essay_count = essay_count or 0

    total_questions = mcq_count + tf_count + essay_count

    try:
        if context_text:
            print(f"Using provided context ({len(context_text)} chars), skipping RAG retriever.")
        else:
            query_text = subject + (" " + topic if topic else "")
            top_chunks = retrieve(query_text, top_k=10)
            if not top_chunks:
                print("Warning: No relevant PDF context found. Using dummy context.")
                top_chunks = [{"content": "No context available. Use general knowledge."}]
            context_text = "\n\n".join([chunk["content"] for chunk in top_chunks])

        # Build prompt requesting all three question types
        prompt = f"""
You are an expert instructor. Generate a mixed exam with exactly {total_questions} questions
about the topic below, at {difficulty} difficulty.

Break down:
- {mcq_count} Multiple-Choice Questions (MCQ) with exactly 4 options
- {tf_count} True/False Questions
- {essay_count} Essay/Short-Answer Questions

Topic: {subject}
Context from PDFs:
{context_text}

Return a single JSON array. Each element must have a "type" field:

MCQ format:
{{"type": "mcq", "question": "...", "options": ["Option A text", "Option B text", "Option C text", "Option D text"], "answer": "A"}}

True/False format:
{{"type": "tf", "question": "...", "answer": "True"}}

Essay format:
{{"type": "essay", "question": "...", "answer": "Key points: ..."}}

IMPORTANT: Output ONLY the JSON array. No extra text, no markdown fences.
        """

        response_text = generate_from_llm(prompt)

        try:
            questions_json = extract_json(response_text)
        except (json.JSONDecodeError, ValueError):
            print("LLM did not return valid JSON. Using dummy questions.")
            questions_json = _dummy_mixed(mcq_count, tf_count, essay_count)

        # Step 7: Save exam in Supabase
        now_iso = datetime.now(timezone.utc).isoformat()
        exam_label = f"{subject}" + (f" – {topic}" if topic else "")
        exam_data = {
            "topic": exam_label,
            "content": (
                f"Auto-generated exam on '{exam_label}' "
                f"({mcq_count} MCQ, {tf_count} T/F, {essay_count} Essay, {difficulty})."
            ),
            "difficulty": difficulty,
            "status": "draft",
            "questions": json.dumps(questions_json),
            "created_at": now_iso,
        }
        supabase.table("exams").insert(exam_data).execute()

        print(f"Exam for '{subject}' saved successfully in Supabase!")
        # Return a clean dict with all info for downstream use
        return {
            "topic": exam_label,
            "subject": subject,
            "difficulty": difficulty,
            "num_questions": len(questions_json),
            "questions": questions_json,
            "created_at": now_iso,
        }

    except Exception as e:
        print("Error generating exam:", e)
        return None


# Example usage

if __name__ == "__main__":
    subject = "Supervised Learning"
    topic = "Classification Algorithms"
    difficulty = "Intermediate"
    exam = generate_exam(subject, topic, num_questions=5, difficulty=difficulty)
    if exam:
        print("\nGenerated Exam Summary:")
        print(f"  Topic     : {exam['topic']}")
        print(f"  Difficulty: {exam['difficulty']}")
        print(f"  Questions : {exam['num_questions']}")
        print(f"  Created At: {exam['created_at']}")
        print("\n Questions:")
        for i, q in enumerate(exam["questions"], 1):
            print(f"\n  Q{i}: {q['question']}")
            for opt in q["options"]:
                print(f"       {opt}")
            print(f"       ✔ Answer: {q['answer']}")