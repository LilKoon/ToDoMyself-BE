import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.core.database import Base

class NotificationTypeEnum(str, enum.Enum):
    TASK_REMINDER = "TASK_REMINDER"
    DAILY_DIGEST = "DAILY_DIGEST"
    DUE_SOON = "DUE_SOON"
    TEST_EMAIL = "TEST_EMAIL"

class NotificationStatusEnum(str, enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"

class UserNotificationSettings(Base):
    __tablename__ = "user_notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    email_notifications_enabled = Column(Boolean, default=True)
    remind_before_minutes = Column(Integer, default=30) # Minutes before due date to trigger reminder
    daily_summary_enabled = Column(Boolean, default=True)
    daily_summary_time = Column(String(10), default="08:00") # Format "HH:MM" e.g., "08:00"
    last_daily_digest_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="notification_settings")

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    todo_id = Column(Integer, ForeignKey("todos.id", ondelete="SET NULL"), nullable=True)
    
    notification_type = Column(SQLEnum(NotificationTypeEnum), nullable=False)
    status = Column(SQLEnum(NotificationStatusEnum), default=NotificationStatusEnum.SENT, nullable=False)
    recipient_email = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="notification_logs")
    todo = relationship("Todo", back_populates="notification_logs")
