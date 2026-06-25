from datetime import datetime

from sqlalchemy import DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserAccount(Base):
    __tablename__ = "user_account"
    __table_args__ = (Index("uq_user_account_username", "username", unique=True),)

    user_id: Mapped[str] = mapped_column(primary_key=True)
    username: Mapped[str]
    password_hash: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    jobs = relationship("TranslationJob", back_populates="user")
    sessions = relationship(
        "AuthSession", back_populates="user", cascade="all, delete-orphan"
    )
