from sqlalchemy import String, Text, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
import uuid

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_post_ids: Mapped[list] = mapped_column(JSON)   # 분석에 사용된 공고 ID 리스트
    stack_analysis: Mapped[dict] = mapped_column(JSON)
    gap_analysis: Mapped[dict] = mapped_column(JSON)
    report_md: Mapped[str] = mapped_column(Text)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())