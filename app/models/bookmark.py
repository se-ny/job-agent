from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
import uuid

class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_post_id: Mapped[str] = mapped_column(String, ForeignKey("job_posts.id"))
    user_profile_id: Mapped[int] = mapped_column()
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())