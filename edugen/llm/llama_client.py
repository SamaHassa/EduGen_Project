import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


def _parse_num_questions(prompt: str) -> int:
    """Extract the total number of questions from the prompt (handles mixed-type prompts)."""
    # Mixed-type prompt: "Generate a mixed exam with exactly N questions"
    match = re.search(r"Generate\s+a\s+mixed\s+exam\s+with\s+exactly\s+(\d+)\s+questions", prompt, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # Legacy MCQ-only prompt: "Generate N multiple-choice questions"
    match = re.search(r"Generate\s+(\d+)\s+multiple", prompt, re.IGNORECASE)
    return int(match.group(1)) if match else 5


def _dynamic_dummy(num_questions: int) -> str:
    """
    Fallback: generate `num_questions` placeholder MCQ items so the
    correct count is always respected even without a real LLM.
    """
    topics = [
        ("What is supervised learning?", ["A learning paradigm with labels", "Unsupervised clustering", "Reinforcement signals only", "None of the above"], "A"),
        ("Which algorithm is used for regression?", ["KNN", "Linear Regression", "SVM", "K-Means"], "B"),
        ("What does overfitting mean?", ["Good generalisation", "Poor generalisation on new data", "Faster training", "Lower loss"], "B"),
        ("Which metric suits classification?", ["MSE", "Accuracy", "RMSE", "MAE"], "B"),
        ("Which is a tree-based model?", ["Linear Regression", "Decision Tree", "K-Means", "PCA"], "B"),
        ("What is the bias-variance tradeoff?", ["Balance complexity vs. error", "Always increase bias", "Ignore variance", "None"], "A"),
        ("Which technique prevents overfitting?", ["Regularisation", "More epochs", "Larger learning rate", "Removing labels"], "A"),
        ("What is cross-validation used for?", ["Model evaluation", "Data augmentation", "Feature encoding", "Label smoothing"], "A"),
        ("Which activation adds non-linearity?", ["ReLU", "Dot product", "Matrix transpose", "Softmax only"], "A"),
        ("What does gradient descent minimise?", ["Loss function", "Accuracy", "Dataset size", "Layer count"], "A"),
        ("Which is an unsupervised method?", ["K-Means clustering", "Logistic regression", "SVM", "Random forest"], "A"),
        ("What is a confusion matrix?", ["Performance table for classifiers", "Type of neural layer", "Loss metric", "None"], "A"),
        ("Which ensemble method uses boosting?", ["AdaBoost", "K-Means", "PCA", "Linear SVM"], "A"),
        ("What does PCA stand for?", ["Principal Component Analysis", "Partial Cluster Aggregation", "Predictive Class Algorithm", "None"], "A"),
        ("What is a hyperparameter?", ["Configured before training", "Learned during training", "The output label", "A dataset column"], "A"),
        ("Which loss for binary classification?", ["Binary cross-entropy", "MSE", "MAE", "Huber loss"], "A"),
        ("What is feature scaling?", ["Normalising input range", "Removing features", "Adding new columns", "None"], "A"),
        ("Which model is interpretable?", ["Decision Tree", "Deep neural network", "Random Forest", "SVM with RBF"], "A"),
        ("What is dropout used for?", ["Regularisation in NNs", "Data loading", "Label encoding", "Activation"], "A"),
        ("Which metric for imbalanced classes?", ["F1-Score", "Raw accuracy", "MSE", "R²"], "A"),
    ]
    questions = []
    for idx in range(num_questions):
        t = topics[idx % len(topics)]
        questions.append({
            "question": t[0],
            "options": t[1],
            "answer": t[2],
        })
    return json.dumps(questions)


def generate_from_llm(prompt: str) -> str:
    """
    Call Groq LLM if GROQ_API_KEY is set; otherwise use the dynamic dummy.
    """
    num_questions = _parse_num_questions(prompt)

    if not GROQ_API_KEY:
        print(f"[llama_client] No GROQ_API_KEY set – using dynamic dummy ({num_questions} questions).")
        return _dynamic_dummy(num_questions)

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert educator. Reply ONLY with valid JSON – no extra text, no markdown fences."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.7,
            max_tokens=4096,
        )
        return chat.choices[0].message.content
    except Exception as exc:
        print(f"[llama_client] Groq API error: {exc}. Falling back to dummy ({num_questions} questions).")
        return _dynamic_dummy(num_questions)
