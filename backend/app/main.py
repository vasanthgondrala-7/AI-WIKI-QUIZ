from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import json  # ✅ REQUIRED

from app.database import get_db
from app.models import Quiz, QuizAttempt
from app import schemas
from app.scraper import scrape_wikipedia, validate_wikipedia_url
from app.llm_quiz_generator import QuizGenerator
from sqlalchemy import text


app = FastAPI(
    title="AI Wiki Quiz Generator",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# -------------------- CORS --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "https://ai-wiki-quiz-generator-delta.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

quiz_generator = QuizGenerator()

# -------------------- ROOT --------------------
@app.get("/")
def root():
    return {"message": "AI Wiki Quiz Generator API"}

# -------------------- GENERATE QUIZ --------------------
@app.post("/generate-quiz", response_model=schemas.QuizResponse)
def generate_quiz(
    quiz_request: schemas.QuizRequest,
    db: Session = Depends(get_db)
):
    if not validate_wikipedia_url(quiz_request.url):
        raise HTTPException(status_code=400, detail="Invalid Wikipedia URL")

    existing = db.query(Quiz).filter(Quiz.url == quiz_request.url).first()
    if existing:
        return {
            "id": existing.id,
            "url": existing.url,
            "title": existing.title,
            **existing.get_quiz_data()
        }

    article_text, title = scrape_wikipedia(quiz_request.url)
    if not article_text:
        raise HTTPException(status_code=400, detail="Failed to scrape article")

    quiz_data = quiz_generator.generate_quiz(article_text)
    if not quiz_data or not quiz_data.quiz:
        raise HTTPException(status_code=500, detail="Quiz generation failed")

    db_quiz = Quiz(
        url=quiz_request.url,
        title=title or "Unknown Title",
        scraped_content=article_text
    )
    db_quiz.set_quiz_data(quiz_data.dict())

    db.add(db_quiz)
    db.commit()
    db.refresh(db_quiz)

    return {
        "id": db_quiz.id,
        "url": db_quiz.url,
        "title": db_quiz.title,
        **quiz_data.dict()
    }

# -------------------- SUBMIT ATTEMPT --------------------
@app.post(
    "/quizzes/{quiz_id}/attempt",
    response_model=schemas.QuizAttemptResponse
)
def submit_attempt(
    quiz_id: int,
    attempt: schemas.QuizAttemptCreate,
    db: Session = Depends(get_db)
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz_data = quiz.get_quiz_data()
    questions = quiz_data.get("quiz", [])

    correct = 0
    for i, q in enumerate(questions):
        if i >= len(attempt.answers):
            break
        if attempt.answers[i].strip() == q["answer"].strip():
            correct += 1

    total = len(questions)
    score = (correct / total) * 100 if total else 0

    db_attempt = QuizAttempt(
        quiz_id=quiz_id,
        score=score,
        correct_answers=correct,
        total_questions=total,
        user_answers=json.dumps(attempt.answers),  # ✅ FIXED
        time_taken=attempt.time_taken
    )

    db.add(db_attempt)
    db.commit()
    db.refresh(db_attempt)

    return {
        "id": db_attempt.id,
        "score": score,
        "correct_answers": correct,
        "total_questions": total,
        "time_taken": db_attempt.time_taken,
        "date_attempted": db_attempt.date_attempted,
        "answers": attempt.answers
    }

# -------------------- QUIZ HISTORY --------------------
@app.get("/quizzes", response_model=List[schemas.QuizHistory])
def quiz_history(db: Session = Depends(get_db)):
    quizzes = db.query(Quiz).order_by(Quiz.date_generated.desc()).all()
    result = []

    for q in quizzes:
        attempts = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == q.id
        ).all()

        result.append({
            "id": q.id,
            "url": q.url,
            "title": q.title,
            "date_generated": q.date_generated,
            "attempts_count": len(attempts),
            "best_score": max([a.score for a in attempts], default=None)
        })

    return result

# -------------------- SINGLE QUIZ --------------------
@app.get("/quizzes/{quiz_id}", response_model=schemas.QuizResponse)
def get_quiz(quiz_id: int, db: Session = Depends(get_db)):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    data = quiz.get_quiz_data()
    return {
        "id": quiz.id,
        "url": quiz.url,
        "title": quiz.title,
        "summary": data.get("summary", ""),
        "key_entities": data.get("key_entities", {}),
        "sections": data.get("sections", []),
        "quiz": data.get("quiz", []),
        "related_topics": data.get("related_topics", [])
    }

# -------------------- HEALTH --------------------
@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "healthy"}

