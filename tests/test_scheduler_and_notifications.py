import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
import pytz

from app.main import app
from app.core.database import init_db, AsyncSessionLocal
from app.models.user import User
from app.models.todo import Todo, StatusEnum, PriorityEnum
from app.models.notification import UserNotificationSettings, NotificationLog
from app.services.scheduler import check_and_send_task_reminders, check_and_send_daily_digests
from sqlalchemy.future import select

@pytest.mark.asyncio
async def test_scheduler_jobs_and_rules():
    await init_db()
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        time_tag = asyncio.get_event_loop().time()
        user_email = f"scheduler_user_{time_tag}@example.com"

        # 1. Register User
        reg_res = await client.post("/api/v1/auth/register", json={
            "email": user_email,
            "full_name": "Scheduler Tester",
            "password": "Password123!",
            "timezone": "Asia/Ho_Chi_Minh"
        })
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = reg_res.json()["user"]["id"]

        now_utc = datetime.now(timezone.utc)

        # 2. Create tasks with different dates to test filtering rules:
        # Task 1: Overdue incomplete task
        overdue_res = await client.post("/api/v1/todos", json={
            "title": "Task 1: Quá hạn",
            "priority": "HIGH",
            "due_date": (now_utc - timedelta(days=2)).isoformat(),
            "status": "TODO"
        }, headers=headers)
        assert overdue_res.status_code == 201

        # Task 2: Task due today
        today_res = await client.post("/api/v1/todos", json={
            "title": "Task 2: Hôm nay",
            "priority": "MEDIUM",
            "due_date": (now_utc + timedelta(hours=2)).isoformat(),
            "status": "TODO"
        }, headers=headers)
        assert today_res.status_code == 201

        # Task 3: Task due tomorrow (within 24h)
        upcoming_res = await client.post("/api/v1/todos", json={
            "title": "Task 3: Ngày mai (trong 24h)",
            "priority": "LOW",
            "due_date": (now_utc + timedelta(hours=18)).isoformat(),
            "status": "TODO"
        }, headers=headers)
        assert upcoming_res.status_code == 201

        # Task 4: Task far away (5 days in the future - RULE: MUST NOT BE INCLUDED IN NOTIFICATION)
        far_res = await client.post("/api/v1/todos", json={
            "title": "Task 4: Xa hơn 1 ngày (5 ngày sau)",
            "priority": "MEDIUM",
            "due_date": (now_utc + timedelta(days=5)).isoformat(),
            "status": "TODO"
        }, headers=headers)
        assert far_res.status_code == 201
        far_todo_id = far_res.json()["id"]

        # Task 5: Task with specific reminder_time right now
        reminder_res = await client.post("/api/v1/todos", json={
            "title": "Task 5: Đến giờ nhắc",
            "priority": "URGENT",
            "reminder_time": (now_utc - timedelta(minutes=1)).isoformat(),
            "status": "TODO"
        }, headers=headers)
        assert reminder_res.status_code == 201
        reminder_todo_id = reminder_res.json()["id"]

        # 3. Test Task Reminder Scheduler Execution
        await check_and_send_task_reminders()

        # Verify that Task 5 is marked as is_reminder_sent = True
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Todo).where(Todo.id == reminder_todo_id))
            t5 = res.scalars().first()
            assert t5 is not None
            assert t5.is_reminder_sent is True

            # Task 4 (far future) must NOT be marked as reminder sent
            res_far = await db.execute(select(Todo).where(Todo.id == far_todo_id))
            t4 = res_far.scalars().first()
            assert t4 is not None
            assert t4.is_reminder_sent is False

        # 4. Test Notification Logs Query
        logs_res = await client.get("/api/v1/notifications/logs", headers=headers)
        assert logs_res.status_code == 200
        logs_list = logs_res.json()
        assert isinstance(logs_list, list)

        print("\nScheduler & Notification rules test PASSED!")
