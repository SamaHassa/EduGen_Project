import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List

from models.exam_grader import load_exam, grade_answers, save_result, evaluate_exam


app = FastAPI(
    title="EduGen Exam API",
    description="AI-powered exam evaluation using Llama-3.3-70b via Groq",
)


class EvaluateRequest(BaseModel):
    exam_id: int = Field(..., description="ID of the exam to evaluate")
    student_name: str = Field(..., description="Full name of the student")
    answers: List[str] = Field(
        ...,
        description="One answer per question — letter for MCQ, True/False for T/F, free text for Essay",
    )


class QuestionOut(BaseModel):
    index: int
    type: str
    question: str
    options: List[str] = []  


class ExamOut(BaseModel):
    exam_id: int
    topic: str
    difficulty: str
    total_questions: int
    questions: List[QuestionOut]


class BreakdownItem(BaseModel):
    question_index: int
    question_type: str
    question: str
    student_answer: str
    correct_answer: str
    is_correct: bool
    points: float
    essay_score: int = None
    essay_feedback: str = None


class EvaluateResponse(BaseModel):
    exam_id: int
    exam_topic: str
    student_name: str
    numerical_score: int
    correct_count: int
    total: int
    ai_feedback: str
    score_breakdown: List[BreakdownItem]


@app.get("/")
def check():
    return {"status": "ok", "message": "EduGen API is live "}


@app.get("/exam/{exam_id}", response_model=ExamOut, tags=["Exam"])
def get_exam(exam_id: int):
    try:
        exam = load_exam(exam_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Exam {exam_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    questions_out = []
    for i, q in enumerate(exam["questions"]):
        questions_out.append(QuestionOut(
            index=i + 1,
            type=q.get("type", "mcq"),
            question=q["question"],
            options=q.get("options", []),
        ))

    return ExamOut(
        exam_id=exam_id,
        topic=exam["topic"],
        difficulty=exam.get("difficulty", "Intermediate"),
        total_questions=len(questions_out),
        questions=questions_out,
    )


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(request: EvaluateRequest):
    """
    Submit student answers and receive a full graded result.

    - MCQ answers  → single letter, e.g. `"B"`
    - T/F answers  → `"True"` or `"False"`
    - Essay answers → free text string
    """
    try:
        exam = load_exam(request.exam_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Exam {request.exam_id} not found.")

    questions = exam["questions"]

    if len(request.answers) != len(questions):
        raise HTTPException(
            status_code=422,
            detail=f"Expected {len(questions)} answers, got {len(request.answers)}.",
        )

    grading = grade_answers(questions, request.answers)
    save_result(request.exam_id, request.student_name, request.answers, grading)

    return EvaluateResponse(
        exam_id=request.exam_id,
        exam_topic=exam["topic"],
        student_name=request.student_name,
        numerical_score=grading["numerical_score"],
        correct_count=grading["correct_count"],
        total=grading["total"],
        ai_feedback=grading["ai_feedback"],
        score_breakdown=grading["score_breakdown"],
    )

    