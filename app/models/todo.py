import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.core.database import Base

class PriorityEnum(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"

class StatusEnum(str, enum.Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(SQLEnum(PriorityEnum), default=PriorityEnum.MEDIUM, nullable=False)
    status = Column(SQLEnum(StatusEnum), default=StatusEnum.TODO, nullable=False, index=True)
    category = Column(String(100), default="General", nullable=False)
    
    start_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    reminder_time = Column(DateTime(timezone=True), nullable=True)
    is_reminder_sent = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Composite Indexes for high-performance querying
    __table_args__ = (
        Index("idx_todos_user_status", "user_id", "status"),
        Index("idx_todos_user_due_date", "user_id", "due_date"),
        Index("idx_todos_user_created_at", "user_id", "created_at"),
        Index("idx_todos_scheduler_remind", "is_reminder_sent", "status", "reminder_time"),
    )

    # Relationships
    owner = relationship("User", back_populates="todos")
    subtasks = relationship("Subtask", back_populates="todo", cascade="all, delete-orphan", order_by="Subtask.order_index")
    notification_logs = relationship("NotificationLog", back_populates="todo", cascade="all, delete-orphan")

class Subtask(Base):
    __tablename__ = "subtasks"

    id = Column(Integer, primary_key=True, index=True)
    todo_id = Column(Integer, ForeignKey("todos.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    is_completed = Column(Boolean, default=False)
    order_index = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    todo = relationship("Todo", back_populates="subtasks")
