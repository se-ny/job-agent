from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    
    # 보유 스택 (예: ["FastAPI", "PostgreSQL", "Python"])
    current_skills = Column(JSON, nullable=False, default=list)
    
    # 경력 개월수
    experience_months = Column(Integer, default=0)
    
    # 자유 형식 자기소개 / 경력 기술
    bio = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())