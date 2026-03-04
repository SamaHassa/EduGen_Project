# 🎓 EduGen — AI-Powered Exam Generator & Grader

> **Turn any PDF into a full exam in seconds. Let AI do the grading.**  
> Built with Llama 3.3 · Groq · Supabase · Streamlit

---

## ✨ What is EduGen?

EduGen is a smart exam platform for instructors and students. Upload a lecture PDF, pick your question mix, and watch **Llama-3.3-70b** generate a complete, topic-aware exam — MCQs, True/False, and Essays — all graded automatically by AI.

No more copy-pasting questions. No more manual grading. Just teach. 🚀

---

## 🔥 Features

| Feature | Details |
|---|---|
| 📄 **PDF-to-Exam** | Upload any lecture PDF → AI reads it → generates unique questions from the actual content |
| 🎯 **Mixed Question Types** | Choose how many MCQ, True/False, and Essay questions you want |
| 🤖 **AI Grading** | MCQ & T/F graded instantly; Essays scored 0–100 by Llama with written feedback |
| 🗄️ **Supabase Backend** | All exams and student submissions saved to the cloud automatically |
| 👤 **Student Names** | Students enter their name — no IDs, no logins |
| 🔍 **RAG Fallback** | No PDF? EduGen searches the knowledge base using vector similarity |
| ⚡ **Groq Speed** | Llama-3.3-70b runs at blazing speed via Groq Cloud |

---

## 🏗️ Project Structure

```
edugen/
├── app.py                  # Streamlit UI (Instructor + Student views)
├── models/
│   ├── exam_generator.py   # Builds the LLM prompt & saves exam to Supabase
│   └── exam_grader.py      # Hybrid grader: string match + LLM-as-a-Judge
├── llm/
│   └── llama_client.py     # Groq API wrapper (Llama-3.3-70b)
├── rag/
│   └── retriever.py        # Vector search over Supabase pdf_chunks table
├── ingestion/
│   ├── pdf_ingest.py       # PDF → text chunks
│   └── embed_to_supabase.py# Embeds chunks → stores in Supabase
└── database/
    └── connection.py       # Supabase client setup
```

---

## 🚀 Quick Start

### 1. Clone & install dependencies

```bash
git clone https://github.com/your-username/edugen.git
cd edugen
pip install streamlit supabase groq PyPDF2 langchain langchain-huggingface
```

### 2. Set your Groq API key

Get a free key at [console.groq.com](https://console.groq.com) then open `edugen/llm/llama_client.py` and paste it:

```python
GROQ_API_KEY = "gsk_your_key_here"
```

### 3. Run the app

```bash
streamlit run edugen/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser. Done! 🎉

---

## 🎓 How It Works

### For Instructors
1. Select **📋 Instructor** in the sidebar
2. Upload a PDF (lecture notes, textbook chapter, anything)
3. Set Subject, Topic, Difficulty, and your question mix (MCQ / T/F / Essay)
4. Click **⚡ Generate Exam**
5. Share the **Exam ID** with your students

### For Students
1. Select **🎒 Student** in the sidebar
2. Enter your name and the Exam ID
3. Answer all questions — radios for MCQ/T/F, text box for essays
4. Click **✅ Submit** and get instant AI feedback with a full breakdown

---

## 🧠 AI Architecture

```
PDF Upload  ──►  PyPDF2 extraction  ──►  RecursiveCharacterTextSplitter
                                               │
                                               ▼
                              Groq (Llama-3.3-70b) ← system prompt
                                               │
                                        JSON question array
                                    [MCQ | T/F | Essay]
                                               │
                              ┌────────────────┼───────────────┐
                              ▼                ▼               ▼
                         Letter match    True/False       LLM-as-Judge
                         (MCQ grader)   (T/F grader)   (0–100 + feedback)
```

---

## 🗄️ Database Schema (Supabase)

| Table | Key Columns |
|---|---|
| `exams` | `id`, `topic`, `difficulty`, `questions` (JSON), `created_at` |
| `submissions` | `exam_id`, `student_answers`, `numerical_score`, `score_breakdown`, `ai_feedback`, `grader_note` |
| `pdf_chunks` | `pdf_name`, `chunk_index`, `content`, `embedding` |

---

## 🛠️ Tech Stack

- **Frontend** — [Streamlit](https://streamlit.io)
- **LLM** — [Llama-3.3-70b-versatile](https://groq.com) via Groq Cloud
- **Database** — [Supabase](https://supabase.com) (PostgreSQL + Storage)
- **PDF Parsing** — PyPDF2
- **Embeddings** — `sentence-transformers/all-MiniLM-L6-v2` (HuggingFace)
- **RAG** — LangChain + cosine similarity vector search

---



