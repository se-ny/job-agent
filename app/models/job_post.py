from sqlalchemy import String, Text, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from typing import Optional
import uuid

class JobPost(Base):
    __tablename__ = "job_posts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(100))
    raw_text: Mapped[str] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    keywords: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 추출된 키워드
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())