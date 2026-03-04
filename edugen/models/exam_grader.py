import sys
import os
import json
from datetime import datetime, timezone

from supabase import create_client, Client

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# Supabase config
    
SUPABASE_URL = "https://jwuxmjwgeqwvryupluod.supabase.co"
SUPABASE_KEY = "sb_secret_aTmKc4oVYuHOGsqRwO4HbQ_2yKZtIUs"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# Load Exam from Supabase

def load_exam(exam_id: int) -> dict:
    """Fetch an exam record from Supabase by ID."""
    resp = supabase.table("exams").select("*").eq("id", exam_id).single().execute()
    exam = resp.data
    if not exam:
        raise ValueError(f"Exam with id={exam_id} not found.")

    # questions may be stored as a JSON string or already a list
    if isinstance(exam["questions"], str):
        exam["questions"] = json.loads(exam["questions"])
    return exam


# Essay grader via Groq

def _grade_essay_with_llm(question: str, model_answer: str, student_text: str) -> dict:
    """Use Groq to score a student essay answer 0-100 and give brief feedback."""
    from llm.llama_client import GROQ_API_KEY
    if not GROQ_API_KEY or not student_text.strip():
        return {"essay_score": 0, "essay_feedback": "No answer provided." if not student_text.strip() else "Essay grading requires a Groq API key."}
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        prompt = (
            f"Question: {question}\n\n"
            f"Model answer / key points: {model_answer}\n\n"
            f"Student's answer: {student_text}\n\n"
            "Score the student's answer from 0 to 100 based on accuracy and completeness. "
            "Reply ONLY with valid JSON: {\"score\": <number>, \"feedback\": \"<one sentence>\"}"
        )
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a strict but fair academic grader. Reply ONLY with valid JSON."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        result = json.loads(chat.choices[0].message.content)
        return {"essay_score": int(result.get("score", 0)), "essay_feedback": result.get("feedback", "")}
    except Exception as e:
        return {"essay_score": 50, "essay_feedback": f"Could not auto-grade essay: {e}"}



# Grade Answers  (MCQ + T/F + Essay)

def grade_answers(questions: list, student_answers: list) -> dict:
    """
    Grade a mixed exam. student_answers is a list aligned with questions:
      - MCQ  → letter string, e.g. "B"
      - T/F  → "True" or "False"
      - Essay → free-text string
    Returns a results dict with breakdown, weighted score, and feedback.
    """
    total = len(questions)
    points_earned = 0.0
    breakdown = []

    for i, question in enumerate(questions):
        q_type = question.get("type", "mcq").lower()
        given = student_answers[i] if i < len(student_answers) else ""

        item = {
            "question_index": i + 1,
            "question_type": q_type,
            "question": question["question"],
            "student_answer": given if given else "(no answer)",
            "correct_answer": question.get("answer", ""),
            "is_correct": False,
            "points": 0.0,
        }

        if q_type == "mcq":
            correct = question["answer"].strip().upper()
            opts = question.get("options", [])
            letter_to_text = {chr(65 + j): opt for j, opt in enumerate(opts)}
            correct_text = letter_to_text.get(correct, "")
            item["correct_answer"] = f"{correct}: {correct_text}" if correct_text else correct

            given_upper = str(given).strip().upper()
            given_text = letter_to_text.get(given_upper, "")
            item["student_answer"] = f"{given_upper}: {given_text}" if (given_upper and given_text) else (given_upper if given_upper else "(no answer)")
            item["is_correct"] = given_upper == correct
            item["points"] = 1.0 if item["is_correct"] else 0.0

        elif q_type == "tf":
            correct = question["answer"].strip().capitalize()   # "True" or "False"
            item["correct_answer"] = correct
            given_cap = str(given).strip().capitalize()
            item["student_answer"] = given_cap if given_cap else "(no answer)"
            item["is_correct"] = given_cap == correct
            item["points"] = 1.0 if item["is_correct"] else 0.0

        elif q_type == "essay":
            result = _grade_essay_with_llm(question["question"], question.get("answer", ""), str(given))
            essay_score = result["essay_score"]          # 0-100
            item["points"] = essay_score / 100.0
            item["is_correct"] = essay_score >= 60
            item["essay_score"] = essay_score
            item["essay_feedback"] = result["essay_feedback"]
            item["correct_answer"] = question.get("answer", "(see key points)")
            item["student_answer"] = str(given) if given else "(no answer)"

        points_earned += item["points"]
        breakdown.append(item)

    numerical_score = int(round((points_earned / total) * 100)) if total > 0 else 0
    correct_count = sum(1 for b in breakdown if b["is_correct"])

    if numerical_score == 100:
        feedback = "Perfect score! Excellent work."
    elif numerical_score >= 80:
        feedback = f"Great job! You scored {numerical_score}% ({points_earned:.1f}/{total} points)."
    elif numerical_score >= 60:
        feedback = f"Good effort. You scored {numerical_score}%. Review the missed topics."
    elif numerical_score >= 40:
        feedback = f"You scored {numerical_score}%. More practice is recommended."
    else:
        feedback = f"You scored {numerical_score}%. Please revisit the material thoroughly."

    return {
        "numerical_score": numerical_score,
        "correct_count": correct_count,
        "total": total,
        "score_breakdown": breakdown,
        "ai_feedback": feedback,
    }


# Save Result to Supabase

def save_result(exam_id: int, student_name: str, student_answers: list, grading: dict) -> dict:
    """Save graded submission to the submissions table."""
    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "exam_id": exam_id,
        # student_id is nullable — we store the human-readable name in grader_note
        "student_answers": json.dumps(student_answers),
        "numerical_score": grading["numerical_score"],
        "score_breakdown": json.dumps(grading["score_breakdown"]),
        "ai_feedback": grading["ai_feedback"],
        "grader_note": f"Student: {student_name} | auto-graded by AI",
        "submitted_at": now_iso,
        "graded_at": now_iso,
    }
    supabase.table("submissions").insert(record).execute()
    return record




# Main grader pipeline

def evaluate_exam(exam_id: int, student_name: str, student_answers: list) -> dict:
    """
    Full pipeline:
        1. Load exam from Supabase
        2. Grade student answers
        3. Save submission to Supabase
        4. Return full result dict
    """
    try:
        print(f"Loading exam {exam_id} from Supabase...")
        exam = load_exam(exam_id)
        questions = exam["questions"]
        print(f"Exam loaded: '{exam['topic']}' ({len(questions)} questions)")

        print("Grading answers...")
        grading = grade_answers(questions, student_answers)

        print("Saving result to Supabase...")
        save_result(exam_id, student_name, student_answers, grading)

        print(f"Result saved! Score: {grading['numerical_score']}%")
        return {
            "exam_id": exam_id,
            "exam_topic": exam["topic"],
            "student_name": student_name,
            **grading,
        }
    except Exception as e:
        print("Error evaluating exam:", e)
        return None



# Example usage

if __name__ == "__main__":
    # Use the latest exam saved by exam_generator.py
    resp = supabase.table("exams").select("id,topic").order("id", desc=True).limit(1).execute()
    if not resp.data:
        print("No exams found in Supabase. Run exam_generator.py first.")
        exit()

    latest_exam = resp.data[0]
    exam_id = latest_exam["id"]
    print(f"Using exam ID={exam_id}: {latest_exam['topic']}\n")

    # Simulate student answers (one letter per question)
    student_answers = ["A", "B", "B", "A", "B"]
    student_name = "Sama Hassan"

    result = evaluate_exam(exam_id, student_name, student_answers)

    if result:
        print("\n--- EXAM RESULT ---")
        print(f"Exam   : {result['exam_topic']}")
        print(f"Student: {result['student_name']}")
        print(f"Score  : {result['numerical_score']}%  ({result['correct_count']}/{result['total']} correct)")
        print(f"Feedback: {result['ai_feedback']}")
        print("\nBreakdown:")
        for item in result["score_breakdown"]:
            status = "CORRECT" if item["is_correct"] else "WRONG"
            print(f"  Q{item['question_index']}: [{status}]  "
                    f"Your answer: {item['student_answer']}  |  "
                    f"Correct: {item['correct_answer']}")
