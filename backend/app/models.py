from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Float, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import json

from app.database import Base


class Quiz(Base):
    __tablename__ = "quizzes"
    __table_args__ = (
        Index("ix_quizzes_url", "url", unique=True),
    )

    id = Column(Integer, primary_key=True)
    url = Column(String(191), nullable=False)   # MySQL-safe
    title = Column(String(255), nullable=False)
    date_generated = Column(DateTime, default=datetime.utcnow)

    scraped_content = Column(Text)
    full_quiz_data = Column(Text)

    attempts = relationship(
        "QuizAttempt",
        back_populates="quiz",
        cascade="all, delete-orphan"
    )

    def set_quiz_data(self, data: dict):
        self.full_quiz_data = json.dumps(data)

    def get_quiz_data(self) -> dict:
        return json.loads(self.full_quiz_data) if self.full_quiz_data else {}


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"))

    score = Column(Float, nullable=False)
    correct_answers = Column(Integer, nullable=False)
    total_questions = Column(Integer, nullable=False)

    user_answers = Column(Text, nullable=False)
    time_taken = Column(Integer, default=0)
    date_attempted = Column(DateTime, default=datetime.utcnow)

    quiz = relationship("Quiz", back_populates="attempts")
