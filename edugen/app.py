# edugen/app.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import io
import streamlit as st
import json
from supabase import create_client, Client
from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter

from models.exam_generator import generate_exam
from models.exam_grader import load_exam, grade_answers, save_result


# ── PDF helpers ───────────────────────────────────────────────────────────────
def extract_text_from_pdf(uploaded_file) -> str:
    """Extract all text from an uploaded PDF file object."""
    reader = PdfReader(io.BytesIO(uploaded_file.read()))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> str:
    """Split text into chunks and return them joined as one context string."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=overlap
    )
    chunks = splitter.split_text(text)
    return "\n\n".join(chunks)

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="EduGen", page_icon="🎓", layout="wide")

# ── Sidebar – role picker ─────────────────────────────────────────────────────
st.sidebar.title("🎓 EduGen")
role = st.sidebar.radio("Who are you?", ["📋 Instructor", "🎒 Student"], index=0)
st.sidebar.markdown("---")

# helper – fetch available exams from Supabase
@st.cache_data(ttl=30)
def fetch_exams():
    resp = supabase.table("exams").select("id,topic,difficulty,created_at") \
                   .order("id", desc=True).limit(50).execute()
    return resp.data or []

# ══════════════════════════════════════════════════════════════════════════════
#  INSTRUCTOR PAGE
# ══════════════════════════════════════════════════════════════════════════════
if role == "📋 Instructor":
    st.title("📋 Instructor – Generate Exam")

    # ── Groq key status banner ────────────────────────────────────────────────
    from llm.llama_client import GROQ_API_KEY


    # ── PDF uploader ──────────────────────────────────────────────────────────
    st.subheader("📄 Upload a PDF (optional)")
    st.caption("Upload your own lecture notes or textbook. The exam will be generated **from its content**. "
                "If you skip this, the existing knowledge base in the database will be used.")

    uploaded_pdf = st.file_uploader("Choose a PDF file", type=["pdf"], label_visibility="collapsed")

    pdf_context  = None   # will hold extracted + chunked text
    pdf_info     = ""

    if uploaded_pdf is not None:
        with st.spinner(f"Reading **{uploaded_pdf.name}** …"):
            raw_text = extract_text_from_pdf(uploaded_pdf)
            if not raw_text.strip():
                st.error("Could not extract text from this PDF. Try a different file.")
            else:
                pdf_context = chunk_text(raw_text)
                word_count  = len(raw_text.split())
                pdf_info    = uploaded_pdf.name
                st.success(f"✅ **{uploaded_pdf.name}** loaded — {word_count:,} words extracted, ready to use as context.")

    st.markdown("---")

    # ── Exam settings form ────────────────────────────────────────────────────
    st.subheader("⚙️ Exam Settings")
    with st.form("gen_form"):
        col1, col2, col4 = st.columns(3)
        subject    = col1.text_input("Subject *", placeholder="e.g. Supervised Learning",
                                     value=os.path.splitext(pdf_info)[0] if pdf_info else "")
        topic      = col2.text_input("Topic (optional)", placeholder="e.g. Classification Algorithms")
        difficulty = col4.selectbox("Difficulty", ["Beginner", "Intermediate", "Advanced"])
        st.markdown("**Question mix**")
        qcol1, qcol2, qcol3 = st.columns(3)
        mcq_q   = qcol1.number_input("MCQ",        min_value=0, max_value=20, value=3, step=1)
        tf_q    = qcol2.number_input("True / False", min_value=0, max_value=20, value=2, step=1)
        essay_q = qcol3.number_input("Essay",       min_value=0, max_value=10, value=1, step=1)
        submitted  = st.form_submit_button("⚡ Generate Exam", use_container_width=True)

    if submitted:
        if not subject.strip():
            st.error("Subject is required.")
        elif (mcq_q + tf_q + essay_q) == 0:
            st.error("Please set at least 1 question.")
        else:
            total_q   = mcq_q + tf_q + essay_q
            src_label = f"from **{pdf_info}**" if pdf_context else "from the knowledge base"
            with st.spinner(f"Generating {total_q} questions ({mcq_q} MCQ / {tf_q} T/F / {essay_q} Essay) {src_label}…"):
                exam = generate_exam(
                    subject.strip(),
                    topic.strip() or None,
                    difficulty=difficulty,
                    context_text=pdf_context,
                    mcq_count=mcq_q,
                    tf_count=tf_q,
                    essay_count=essay_q,
                )
            if exam:
                resp   = supabase.table("exams").select("id").order("id", desc=True).limit(1).execute()
                new_id = resp.data[0]["id"] if resp.data else "?"
                st.success(f"Exam created! Share **Exam ID `{new_id}`** with your students.")
                st.balloons()

                st.subheader(f"📋 Preview – {exam['topic']}")
                st.caption(f"Difficulty: {exam['difficulty']}  |  {mcq_q} MCQ · {tf_q} T/F · {essay_q} Essay"
                           + (f"  |  Source: {pdf_info}" if pdf_info else ""))
                for i, q in enumerate(exam["questions"], 1):
                    q_type = q.get("type", "mcq")
                    badge  = {"mcq": " MCQ", "tf": " T/F", "essay": " Essay"}.get(q_type, "")
                    with st.expander(f"{badge}  Q{i}: {q['question']}"):
                        if q_type == "mcq":
                            for opt in q.get("options", []):
                                st.write(f"- {opt}")
                            ans_letter = q["answer"].strip().upper()
                            opts = q.get("options", [])
                            letter_to_text = {chr(65 + j): opt for j, opt in enumerate(opts)}
                            ans_text = letter_to_text.get(ans_letter, "")
                            ans_display = f"{ans_letter}: {ans_text}" if ans_text else ans_letter
                            st.success(f"✔ Correct answer: **{ans_display}**")
                        elif q_type == "tf":
                            st.success(f"✔ Correct answer: **{q['answer']}**")
                        else:
                            st.info(f"📝 Model answer / key points: {q.get('answer', '')}")
            else:
                st.error("Exam generation failed. Check the console for details.")

    # ── Recent exams table ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📚 Recent Exams")
    exams = fetch_exams()
    if exams:
        st.dataframe(exams, use_container_width=True,
                        column_config={"id": "ID", "topic": "Topic",
                                    "difficulty": "Difficulty", "created_at": "Created At"})
    else:
        st.info("No exams found yet.")

# ══════════════════════════════════════════════════════════════════════════════
#  STUDENT PAGE
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.title("🎒 Student – Take Exam")

    # Step 1 – identify
    with st.form("student_id_form"):
        col1, col2 = st.columns(2)
        student_name_input = col1.text_input("Your Full Name", placeholder="e.g. Ahmed Ali")
        exam_id_input      = col2.number_input("Exam ID (given by instructor)", min_value=1, step=1, value=1)
        load_btn           = st.form_submit_button("📥 Load Exam", use_container_width=True)

    if load_btn or "exam_loaded" in st.session_state:
        # load exam once and cache in session
        if load_btn:
            if not student_name_input.strip():
                st.error("Please enter your full name before loading the exam.")
                st.stop()
            try:
                st.session_state["exam"]         = load_exam(int(exam_id_input))
                st.session_state["student_name"] = student_name_input.strip()
                st.session_state["exam_loaded"]  = True
                st.session_state.pop("result", None)   # clear old result
            except Exception as e:
                st.error(f"Could not load exam: {e}")
                st.stop()

        exam         = st.session_state.get("exam")
        student_name = st.session_state.get("student_name")

        if not exam:
            st.stop()

        questions = exam["questions"]
        st.subheader(f"📝 {exam['topic']}")
        st.caption(f"Student: **{student_name}**  |  Difficulty: {exam.get('difficulty','—')}  |  Questions: {len(questions)}")
        st.markdown("---")

        # Step 2 – answer questions (only show if not yet submitted)
        if "result" not in st.session_state:
            with st.form("answer_form"):
                raw_answers = []   # stores raw input per question
                meta        = []   # stores (q_type, keys, opts) for mapping
                for i, q in enumerate(questions):
                    q_type = q.get("type", "mcq")
                    badge  = {"mcq": " MCQ", "tf": " T/F", "essay": " Essay"}.get(q_type, "")
                    st.markdown(f"**{badge} &nbsp; Q{i+1}. {q['question']}**")

                    if q_type == "mcq":
                        opts = q.get("options", [])
                        keys = [chr(65 + j) for j in range(len(opts))]
                        choice = st.radio("", opts, key=f"q_{i}", index=None,
                                          label_visibility="collapsed")
                        raw_answers.append(choice)
                        meta.append(("mcq", keys, opts))

                    elif q_type == "tf":
                        choice = st.radio("", ["True", "False"], key=f"q_{i}", index=None,
                                          label_visibility="collapsed")
                        raw_answers.append(choice)
                        meta.append(("tf", [], []))

                    else:   # essay
                        text = st.text_area("Your answer", key=f"q_{i}",
                                            placeholder="Write your answer here…",
                                            label_visibility="collapsed")
                        raw_answers.append(text)
                        meta.append(("essay", [], []))

                    st.markdown("")

                submit_btn = st.form_submit_button("Submit Answers", use_container_width=True)

            if submit_btn:
                # Validate MCQ and T/F must be answered; essays are optional
                unanswered = [
                    i + 1 for i, (raw, (q_type, _, _)) in enumerate(zip(raw_answers, meta))
                    if q_type in ("mcq", "tf") and not raw
                ]
                if unanswered:
                    st.error(f"Please answer all questions before submitting. Unanswered: Q{', Q'.join(map(str, unanswered))}")
                else:
                    # Convert each raw answer to its canonical form
                    final_answers = []
                    for raw, (q_type, keys, opts) in zip(raw_answers, meta):
                        if q_type == "mcq":
                            final_answers.append(keys[opts.index(raw)] if raw in opts else raw or "")
                        else:
                            final_answers.append(raw or "")

                    with st.spinner("Grading your answers… (essays are scored by AI, may take a moment)"):
                        grading = grade_answers(questions, final_answers)
                        save_result(exam["id"], student_name, final_answers, grading)
                        st.session_state["result"]          = grading
                        st.session_state["student_answers"] = final_answers
                    st.rerun()

        # Step 3 – show results
        if "result" in st.session_state:
            result = st.session_state["result"]
            score  = result["numerical_score"]

            st.markdown("---")
            st.subheader("🏆 Your Results")
            st.caption("✅ Your results have been saved to the database.")

            col1, col2, col3 = st.columns(3)
            col1.metric("Score", f"{score}%")
            col2.metric("Correct / Passed", f"{result['correct_count']} / {result['total']}")
            col3.metric("Student", student_name)

            if score == 100:
                st.success(result["ai_feedback"])
            elif score >= 60:
                st.info(result["ai_feedback"])
            else:
                st.warning(result["ai_feedback"])

            st.progress(score / 100)

            st.markdown("### Question Breakdown")
            for item in result["score_breakdown"]:
                q_type = item.get("question_type", "mcq")
                badge  = {"mcq": " MCQ", "tf": " T/F", "essay": " Essay"}.get(q_type, "")
                icon   = "✅" if item["is_correct"] else ("⚠️" if q_type == "essay" else "❌")
                with st.expander(f"{icon} {badge}  Q{item['question_index']}: {item['question']}"):
                    if q_type == "essay":
                        essay_score = item.get("essay_score", 0)
                        st.write(f"**Your answer:** {item['student_answer']}")
                        st.write(f"**Key points / Model answer:** {item['correct_answer']}")
                        st.write(f"**AI Score:** {essay_score}/100")
                        if essay_score >= 60:
                            st.success(f"✅ {item.get('essay_feedback', '')}")
                        else:
                            st.warning(f"⚠️ {item.get('essay_feedback', '')}")
                    else:
                        col_a, col_b = st.columns(2)
                        col_a.write(f"**Your answer:** {item['student_answer']}")
                        col_b.write(f"**Correct answer:** {item['correct_answer']}")
                        if item["is_correct"]:
                            st.success("Correct!")
                        else:
                            st.error(f"Wrong. The correct answer was **{item['correct_answer']}**.")

            if st.button("🔄 Take Another Exam"):
                for key in ["exam", "exam_loaded", "result", "student_answers"]:
                    st.session_state.pop(key, None)
                st.rerun()


