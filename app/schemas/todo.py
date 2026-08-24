from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from app.models.todo import PriorityEnum, StatusEnum

# Subtask schemas
class SubtaskBase(BaseModel):
    title: str
    is_completed: bool = False
    order_index: int = 0

class SubtaskCreate(SubtaskBase):
    pass

class SubtaskUpdate(BaseModel):
    title: Optional[str] = None
    is_completed: Optional[bool] = None
    order_index: Optional[int] = None

class SubtaskOut(SubtaskBase):
    id: int
    todo_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Todo schemas
class TodoBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: PriorityEnum = PriorityEnum.MEDIUM
    status: StatusEnum = StatusEnum.TODO
    category: str = "General"
    due_date: Optional[datetime] = None
    reminder_time: Optional[datetime] = None

class TodoCreate(TodoBase):
    subtasks: Optional[List[SubtaskCreate]] = []

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[PriorityEnum] = None
    status: Optional[StatusEnum] = None
    category: Optional[str] = None
    due_date: Optional[datetime] = None
    reminder_time: Optional[datetime] = None
    is_reminder_sent: Optional[bool] = None

class TodoStatusUpdate(BaseModel):
    status: StatusEnum

class TodoOut(TodoBase):
    id: int
    user_id: int
    is_reminder_sent: bool
    created_at: datetime
    updated_at: datetime
    subtasks: List[SubtaskOut] = []

    model_config = ConfigDict(from_attributes=True)

class TodoStats(BaseModel):
    total_todos: int
    completed_todos: int
    pending_todos: int
    in_progress_todos: int
    overdue_todos: int
    due_today_todos: int
    upcoming_24h_todos: int
    completion_rate: float
