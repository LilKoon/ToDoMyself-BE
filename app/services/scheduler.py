import pytz
import logging
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.todo import Todo, Subtask, StatusEnum
from app.models.notification import UserNotificationSettings, NotificationLog, NotificationTypeEnum, NotificationStatusEnum
from app.services.email_service import send_task_reminder_email, send_daily_digest_email

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def check_and_send_task_reminders():
    """Job to check individual task reminders every 1 minute"""
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

            for todo in todos:
                user = todo.owner
                if not user or not user.is_active:
                    continue

                settings = user.notification_settings
                if not settings or not settings.email_notifications_enabled:
                    continue

                should_remind = False

                # Case 1: Specific reminder_time has arrived
                if todo.reminder_time and todo.reminder_time <= now_utc:
                    should_remind = True
                
                # Case 2: Due date is approaching based on remind_before_minutes
                elif todo.due_date:
                    remind_window = now_utc + timedelta(minutes=settings.remind_before_minutes)
                    if todo.due_date <= remind_window and todo.due_date >= (now_utc - timedelta(hours=2)):
                        should_remind = True

                if should_remind:
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

                user_local_now = now_utc.astimezone(user_tz)
                current_time_str = user_local_now.strftime("%H:%M") # e.g. "08:00"
                scheduled_time_str = settings.daily_summary_time or "08:00"

                # Check if already sent today in user's timezone
                already_sent_today = False
                if settings.last_daily_digest_sent_at:
                    last_sent_local = settings.last_daily_digest_sent_at.astimezone(user_tz)
                    if last_sent_local.date() == user_local_now.date():
                        already_sent_today = True

                # Compare hours and minutes
                if not already_sent_today and current_time_str == scheduled_time_str:
                    logger.info(f"Preparing daily digest email for user {user.email} (TZ: {tz_name}, Time: {current_time_str})")
                    
                    # Group user tasks according to rules
                    start_of_today = user_local_now.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_of_today = user_local_now.replace(hour=23, minute=59, second=59, microsecond=999999)
                    next_24h = user_local_now + timedelta(hours=24)

                    overdue_tasks = []
                    today_tasks = []
                    upcoming_24h_tasks = []

                    for t in user.todos:
                        if t.status == StatusEnum.COMPLETED:
                            continue
                        
                        task_dict = {
                            "id": t.id,
                            "title": t.title,
                            "priority": t.priority.value,
                            "category": t.category,
                            "due_date": t.due_date.isoformat() if t.due_date else None
                        }

                        if not t.due_date:
                            # Tasks with no due date can be listed under today if created recently
                            today_tasks.append(task_dict)
                            continue

                        # Convert task due_date to user timezone
                        t_due_local = t.due_date.astimezone(user_tz)

                        if t_due_local < start_of_today:
                            overdue_tasks.append(task_dict)
                        elif start_of_today <= t_due_local <= end_of_today:
                            today_tasks.append(task_dict)
                        elif end_of_today < t_due_local <= next_24h:
                            upcoming_24h_tasks.append(task_dict)
                        # Tasks further than 24h / 1 day are purposely NOT sent as per user rule!

                    # Send email
                    res = await send_daily_digest_email(
                        to_email=user.email,
                        user_name=user.full_name,
                        overdue_tasks=overdue_tasks,
                        today_tasks=today_tasks,
                        upcoming_24h_tasks=upcoming_24h_tasks
                    )

                    # Update last sent timestamp
                    settings.last_daily_digest_sent_at = now_utc
                    
                    # Log notification
                    log_entry = NotificationLog(
                        user_id=user.id,
                        notification_type=NotificationTypeEnum.DAILY_DIGEST,
                        status=NotificationStatusEnum.SENT if res.get("success") else NotificationStatusEnum.FAILED,
                        recipient_email=user.email,
                        subject=f"🌅 Kế hoạch công việc hôm nay của bạn",
                        error_message=res.get("error") if not res.get("success") else None,
                        sent_at=now_utc
                    )
                    db.add(log_entry)

            await db.commit()
        except Exception as e:
            logger.error(f"Error in daily digest scheduler job: {e}", exc_info=True)
            await db.rollback()

def start_scheduler():
    """Start APScheduler with interval jobs"""
    if not scheduler.running:
        scheduler.add_job(
            check_and_send_task_reminders,
            trigger=IntervalTrigger(seconds=60),
            id="task_reminders_job",
            replace_existing=True
        )
        scheduler.add_job(
            check_and_send_daily_digests,
            trigger=IntervalTrigger(seconds=60), # Check every 60s for matching minute
            id="daily_digest_job",
            replace_existing=True
        )
        scheduler.start()
        logger.info("APScheduler started successfully with task_reminders and daily_digest jobs.")

def shutdown_scheduler():
    """Shutdown APScheduler cleanly"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shutdown successfully.")
