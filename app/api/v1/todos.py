from datetime import datetime, timezone, timedelta
from typing import List, Optional
import pytz
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, or_, and_

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.todo import Todo, Subtask, PriorityEnum, StatusEnum
from app.schemas.todo import (
    TodoCreate, TodoUpdate, TodoStatusUpdate, TodoOut, TodoStats,
    SubtaskCreate, SubtaskUpdate, SubtaskOut
)

router = APIRouter(prefix="/todos", tags=["Todos"])

@router.get("", response_model=List[TodoOut])
async def get_todos(
    status: Optional[StatusEnum] = None,
    priority: Optional[PriorityEnum] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    filter_type: Optional[str] = Query(None, description="today, upcoming, overdue, completed"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Todo)
        .options(selectinload(Todo.subtasks))
        .where(Todo.user_id == current_user.id)
    )

    if status:
        stmt = stmt.where(Todo.status == status)
    if priority:
        stmt = stmt.where(Todo.priority == priority)
    if category and category != "All":
        stmt = stmt.where(Todo.category == category)
    if search:
        search_pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Todo.title).like(search_pattern),
                func.lower(Todo.description).like(search_pattern)
            )
        )

    # Date-based filters based on user's timezone
    if filter_type:
        tz_name = current_user.timezone or "Asia/Ho_Chi_Minh"
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.timezone("Asia/Ho_Chi_Minh")
        
        now_local = datetime.now(timezone.utc).astimezone(user_tz)
        start_of_today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        next_24h = now_local + timedelta(hours=24)

        if filter_type == "today":
            stmt = stmt.where(
                and_(
                    Todo.status != StatusEnum.COMPLETED,
                    or_(
                        and_(Todo.due_date >= start_of_today, Todo.due_date <= end_of_today),
                        Todo.due_date.is_(None)
                    )
                )
            )
        elif filter_type == "overdue":
            stmt = stmt.where(
                and_(
                    Todo.status != StatusEnum.COMPLETED,
                    Todo.due_date < start_of_today
                )
            )
        elif filter_type == "upcoming":
            stmt = stmt.where(
                and_(
                    Todo.status != StatusEnum.COMPLETED,
                    Todo.due_date > end_of_today,
                    Todo.due_date <= next_24h
                )
            )
        elif filter_type == "completed":
            stmt = stmt.where(Todo.status == StatusEnum.COMPLETED)

    # Order by priority and due_date
    stmt = stmt.order_by(Todo.created_at.desc())
    result = await db.execute(stmt)
    todos = result.scalars().all()
    return todos

@router.post("", response_model=TodoOut, status_code=status.HTTP_201_CREATED)
async def create_todo(
    todo_in: TodoCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Auto-calculate reminder_time if not set but due_date is provided
    reminder_time = todo_in.reminder_time
    if not reminder_time and todo_in.due_date:
        # Load user settings for default remind_before_minutes
        stmt = select(User).options(selectinload(User.notification_settings)).where(User.id == current_user.id)
        res = await db.execute(stmt)
        u = res.scalars().first()
        remind_mins = u.notification_settings.remind_before_minutes if (u and u.notification_settings) else 30
        reminder_time = todo_in.due_date - timedelta(minutes=remind_mins)

    new_todo = Todo(
        user_id=current_user.id,
        title=todo_in.title,
        description=todo_in.description,
        priority=todo_in.priority,
        status=todo_in.status,
        category=todo_in.category or "General",
        due_date=todo_in.due_date,
        reminder_time=reminder_time,
        is_reminder_sent=False
    )
    db.add(new_todo)
    await db.flush()

    if todo_in.subtasks:
        for idx, s in enumerate(todo_in.subtasks):
            subtask = Subtask(
                todo_id=new_todo.id,
                title=s.title,
                is_completed=s.is_completed,
                order_index=s.order_index if s.order_index else idx
            )
            db.add(subtask)

    await db.commit()
    
    # Reload with subtasks
    stmt = select(Todo).options(selectinload(Todo.subtasks)).where(Todo.id == new_todo.id)
    result = await db.execute(stmt)
    return result.scalars().first()

@router.get("/stats/summary", response_model=TodoStats)
async def get_todo_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    tz_name = current_user.timezone or "Asia/Ho_Chi_Minh"
    try:
        user_tz = pytz.timezone(tz_name)
    except Exception:
        user_tz = pytz.timezone("Asia/Ho_Chi_Minh")

    now_local = datetime.now(timezone.utc).astimezone(user_tz)
    start_of_today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
    next_24h = now_local + timedelta(hours=24)

    stmt = select(Todo).where(Todo.user_id == current_user.id)
    result = await db.execute(stmt)
    all_todos = result.scalars().all()

    total = len(all_todos)
    completed = sum(1 for t in all_todos if t.status == StatusEnum.COMPLETED)
    in_progress = sum(1 for t in all_todos if t.status == StatusEnum.IN_PROGRESS)
    pending = sum(1 for t in all_todos if t.status == StatusEnum.TODO)
    
    overdue = 0
    due_today = 0
    upcoming_24h = 0

    for t in all_todos:
        if t.status != StatusEnum.COMPLETED and t.due_date:
            t_due = t.due_date.astimezone(user_tz)
            if t_due < start_of_today:
                overdue += 1
            elif start_of_today <= t_due <= end_of_today:
                due_today += 1
            elif end_of_today < t_due <= next_24h:
                upcoming_24h += 1

    completion_rate = round((completed / total * 100), 1) if total > 0 else 0.0

    return TodoStats(
        total_todos=total,
        completed_todos=completed,
        pending_todos=pending,
        in_progress_todos=in_progress,
        overdue_todos=overdue,
        due_today_todos=due_today,
        upcoming_24h_todos=upcoming_24h,
        completion_rate=completion_rate
    )

@router.get("/{todo_id}", response_model=TodoOut)
async def get_todo(
    todo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Todo).options(selectinload(Todo.subtasks)).where(Todo.id == todo_id, Todo.user_id == current_user.id)
    result = await db.execute(stmt)
    todo = result.scalars().first()
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy công việc.")
    return todo

@router.put("/{todo_id}", response_model=TodoOut)
async def update_todo(
    todo_id: int,
    todo_update: TodoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Todo).options(selectinload(Todo.subtasks)).where(Todo.id == todo_id, Todo.user_id == current_user.id)
    result = await db.execute(stmt)
    todo = result.scalars().first()
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy công việc.")

    if todo_update.title is not None:
        todo.title = todo_update.title
    if todo_update.description is not None:
        todo.description = todo_update.description
    if todo_update.priority is not None:
        todo.priority = todo_update.priority
    if todo_update.status is not None:
        todo.status = todo_update.status
    if todo_update.category is not None:
        todo.category = todo_update.category
    if todo_update.start_date is not None:
        todo.start_date = todo_update.start_date
    if todo_update.due_date is not None:
        todo.due_date = todo_update.due_date
    if todo_update.reminder_time is not None:
        todo.reminder_time = todo_update.reminder_time
        todo.is_reminder_sent = False # Reset flag if reminder time changed
    if todo_update.is_reminder_sent is not None:
        todo.is_reminder_sent = todo_update.is_reminder_sent

    # Synchronize subtasks if provided
    if todo_update.subtasks is not None:
        from sqlalchemy import delete
        await db.execute(delete(Subtask).where(Subtask.todo_id == todo.id))
        for idx, s in enumerate(todo_update.subtasks):
            subtask = Subtask(
                todo_id=todo.id,
                title=s.title,
                is_completed=s.is_completed,
                order_index=s.order_index if s.order_index else idx
            )
            db.add(subtask)

    await db.commit()
    
    # Reload with fresh subtasks
    stmt = select(Todo).options(selectinload(Todo.subtasks)).where(Todo.id == todo.id)
    result = await db.execute(stmt)
    return result.scalars().first()


@router.patch("/{todo_id}/status", response_model=TodoOut)
async def update_todo_status(
    todo_id: int,
    status_in: TodoStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Todo).options(selectinload(Todo.subtasks)).where(Todo.id == todo_id, Todo.user_id == current_user.id)
    result = await db.execute(stmt)
    todo = result.scalars().first()
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy công việc.")

    todo.status = status_in.status
    await db.commit()
    await db.refresh(todo)
    return todo

@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(
    todo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Todo).where(Todo.id == todo_id, Todo.user_id == current_user.id)
    result = await db.execute(stmt)
    todo = result.scalars().first()
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy công việc.")

    await db.delete(todo)
    await db.commit()
    return None

# Subtask endpoints
@router.post("/{todo_id}/subtasks", response_model=SubtaskOut, status_code=status.HTTP_201_CREATED)
async def create_subtask(
    todo_id: int,
    subtask_in: SubtaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Todo).where(Todo.id == todo_id, Todo.user_id == current_user.id)
    result = await db.execute(stmt)
    todo = result.scalars().first()
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy công việc cha.")

    subtask = Subtask(
        todo_id=todo.id,
        title=subtask_in.title,
        is_completed=subtask_in.is_completed,
        order_index=subtask_in.order_index
    )
    db.add(subtask)
    await db.commit()
    await db.refresh(subtask)
    return subtask

@router.patch("/subtasks/{subtask_id}", response_model=SubtaskOut)
async def update_subtask(
    subtask_id: int,
    subtask_update: SubtaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Subtask)
        .join(Todo)
        .where(Subtask.id == subtask_id, Todo.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    subtask = result.scalars().first()
    if not subtask:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy việc con.")

    if subtask_update.title is not None:
        subtask.title = subtask_update.title
    if subtask_update.is_completed is not None:
        subtask.is_completed = subtask_update.is_completed
    if subtask_update.order_index is not None:
        subtask.order_index = subtask_update.order_index

    await db.commit()
    await db.refresh(subtask)
    return subtask

@router.delete("/subtasks/{subtask_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subtask(
    subtask_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Subtask)
        .join(Todo)
        .where(Subtask.id == subtask_id, Todo.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    subtask = result.scalars().first()
    if not subtask:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy việc con.")

    await db.delete(subtask)
    await db.commit()
    return None
