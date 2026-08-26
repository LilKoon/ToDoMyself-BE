import pytz
import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import delete


from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.todo import Todo, Subtask, StatusEnum
from app.models.notification import UserNotificationSettings, NotificationLog, NotificationTypeEnum, NotificationStatusEnum
from app.models.otp import EmailOTP
from app.services.email_service import send_task_reminder_email, send_daily_digest_email

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def process_single_task_reminder(
    sem: asyncio.Semaphore,
    todo: Todo,
    user: User,
    now_utc: datetime,
    db
):
    """Worker task to send a single reminder email under concurrency limit"""
    async with sem:
        logger.info(f"Triggering email reminder for task '{todo.title}' (User: {user.email})")
        
        todo_dict = {
            "id": todo.id,
            "title": todo.title,
            "description": todo.description,
            "priority": todo.priority.value,
            "category": todo.category,
            "due_date": todo.due_date.isoformat() if todo.due_date else None,
            "subtasks": [{"title": s.title, "is_completed": s.is_completed} for s in todo.subtasks]
        }

        res = await send_task_reminder_email(
            to_email=user.email,
            user_name=user.full_name,
            todo=todo_dict
        )

        # Mark as sent to prevent duplicate sending
        todo.is_reminder_sent = True
        
        # Log notification
        log_entry = NotificationLog(
            user_id=user.id,
            todo_id=todo.id,
            notification_type=NotificationTypeEnum.TASK_REMINDER,
            status=NotificationStatusEnum.SENT if res.get("success") else NotificationStatusEnum.FAILED,
            recipient_email=user.email,
            subject=f"⏰ Nhắc nhở công việc: {todo.title}",
            error_message=res.get("error") if not res.get("success") else None,
            sent_at=now_utc
        )
        db.add(log_entry)

def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

async def check_and_send_task_reminders():
    """Job to check individual task reminders every 1 minute with parallel sending"""
    async with AsyncSessionLocal() as db:
        try:
            now_utc = datetime.now(timezone.utc)
            
            # Query todos that are not completed and reminder not yet sent
            stmt = (
                select(Todo)
                .options(selectinload(Todo.owner).selectinload(User.notification_settings), selectinload(Todo.subtasks))
                .where(
                    Todo.status != StatusEnum.COMPLETED,
                    Todo.is_reminder_sent == False,
                )
            )
            result = await db.execute(stmt)
            todos = result.scalars().all()

            tasks_to_execute = []
            sem = asyncio.Semaphore(10) # Max 10 parallel emails sent simultaneously

            for todo in todos:
                user = todo.owner
                if not user or not user.is_active:
                    continue

                settings = user.notification_settings
                if not settings or not settings.email_notifications_enabled:
                    continue

                should_remind = False

                rem_time = to_utc(todo.reminder_time)
                d_date = to_utc(todo.due_date)

                # Case 1: Specific reminder_time has arrived
                if rem_time and rem_time <= now_utc:
                    should_remind = True
                
                # Case 2: Due date is approaching based on remind_before_minutes
                elif d_date:
                    remind_window = now_utc + timedelta(minutes=settings.remind_before_minutes)
                    if d_date <= remind_window and d_date >= (now_utc - timedelta(hours=2)):
                        should_remind = True

                if should_remind:
                    tasks_to_execute.append(
                        process_single_task_reminder(sem, todo, user, now_utc, db)
                    )


            if tasks_to_execute:
                await asyncio.gather(*tasks_to_execute)
                await db.commit()

        except Exception as e:
            logger.error(f"Error in task reminder job: {e}", exc_info=True)
            await db.rollback()

async def check_and_send_daily_digests():
    """Job to check daily digest for each user based on their custom timezone and scheduled time"""
    async with AsyncSessionLocal() as db:
        try:
            now_utc = datetime.now(timezone.utc)
            
            # Get all active users with notification settings and their incomplete tasks
            stmt = (
                select(User)
                .options(selectinload(User.notification_settings), selectinload(User.todos))
                .where(User.is_active == True)
            )
            result = await db.execute(stmt)
            users = result.scalars().all()

            for user in users:
                settings = user.notification_settings
                if not settings or not settings.email_notifications_enabled or not settings.daily_summary_enabled:
                    continue

                # Parse user timezone
                tz_name = user.timezone or "Asia/Ho_Chi_Minh"
                try:
                    user_tz = pytz.timezone(tz_name)
                except Exception:
                    user_tz = pytz.timezone("Asia/Ho_Chi_Minh")

                user_now = now_utc.astimezone(user_tz)
                
                # Match user's configured daily digest time (hour & minute)
                scheduled_time_str = settings.daily_summary_time or "08:00"
                try:
                    sched_hour, sched_minute = map(int, scheduled_time_str.split(":"))
                except ValueError:
                    sched_hour, sched_minute = 8, 0

                if user_now.hour != sched_hour or user_now.minute != sched_minute:
                    continue

                # Check if already sent today in user's timezone
                start_of_user_today = user_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                
                stmt_log = select(NotificationLog).where(
                    NotificationLog.user_id == user.id,
                    NotificationLog.notification_type == NotificationTypeEnum.DAILY_DIGEST,
                    NotificationLog.sent_at >= start_of_user_today
                )
                res_log = await db.execute(stmt_log)
                if res_log.scalars().first():
                    continue  # Already sent today

                # Classify user's todos for digest
                active_todos = [t for t in user.todos if t.status != StatusEnum.COMPLETED]
                if not active_todos:
                    continue # Skip if user has no pending tasks

                start_of_today_tz = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_today_tz = user_now.replace(hour=23, minute=59, second=59, microsecond=999999)
                next_48h_tz = user_now + timedelta(hours=48)

                overdue_tasks = []
                today_tasks = []
                upcoming_tasks = []

                for t in active_todos:
                    if not t.due_date:
                        continue
                    t_due = to_utc(t.due_date).astimezone(user_tz)
                    t_dict = {
                        "id": t.id,
                        "title": t.title,
                        "priority": t.priority.value,
                        "category": t.category,
                        "due_date": t.due_date.isoformat()
                    }

                    if t_due < start_of_today_tz:
                        overdue_tasks.append(t_dict)
                    elif start_of_today_tz <= t_due <= end_of_today_tz:
                        today_tasks.append(t_dict)
                    elif end_of_today_tz < t_due <= next_48h_tz:
                        upcoming_tasks.append(t_dict)

                if not overdue_tasks and not today_tasks and not upcoming_tasks:
                    continue

                logger.info(f"Sending daily digest email to {user.email}")
                res = await send_daily_digest_email(
                    to_email=user.email,
                    user_name=user.full_name,
                    overdue_tasks=overdue_tasks,
                    today_tasks=today_tasks,
                    upcoming_tasks=upcoming_tasks
                )

                log_entry = NotificationLog(
                    user_id=user.id,
                    notification_type=NotificationTypeEnum.DAILY_DIGEST,
                    status=NotificationStatusEnum.SENT if res.get("success") else NotificationStatusEnum.FAILED,
                    recipient_email=user.email,
                    subject=f"📋 Tổng hợp công việc ngày {user_now.strftime('%d/%m/%Y')} - Smart Todo Hub",
                    error_message=res.get("error") if not res.get("success") else None,
                    sent_at=now_utc
                )
                db.add(log_entry)

            await db.commit()
        except Exception as e:
            logger.error(f"Error in daily digest job: {e}", exc_info=True)
            await db.rollback()

async def cleanup_expired_otps():
    """Clean up expired and used OTPs older than 24 hours"""
    async with AsyncSessionLocal() as db:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            await db.execute(delete(EmailOTP).where(EmailOTP.created_at < cutoff))
            await db.commit()
            logger.info("Expired OTPs cleanup completed successfully.")
        except Exception as e:
            logger.error(f"Error in cleanup_expired_otps job: {e}", exc_info=True)
            await db.rollback()

def start_scheduler():
    """Start APScheduler jobs"""
    if not scheduler.running:
        # Job 1: Check task reminders every 1 minute
        scheduler.add_job(
            check_and_send_task_reminders,
            trigger=IntervalTrigger(minutes=1),
            id="task_reminders_job",
            name="Check and send task reminders",
            replace_existing=True
        )

        # Job 2: Check daily digests every 1 minute
        scheduler.add_job(
            check_and_send_daily_digests,
            trigger=IntervalTrigger(minutes=1),
            id="daily_digest_job",
            name="Check and send daily digests",
            replace_existing=True
        )

        # Job 3: Clean up expired OTPs every 12 hours
        scheduler.add_job(
            cleanup_expired_otps,
            trigger=IntervalTrigger(hours=12),
            id="cleanup_otps_job",
            name="Clean up expired OTPs",
            replace_existing=True
        )

        scheduler.start()
        logger.info("APScheduler started with 3 background automation jobs.")

def shutdown_scheduler():
    """Gracefully shutdown APScheduler"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
