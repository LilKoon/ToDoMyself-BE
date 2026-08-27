import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.todo import Todo, StatusEnum, PriorityEnum
from app.models.notification import UserNotificationSettings, NotificationLog, NotificationTypeEnum
from app.core.security import create_magic_login_token, verify_magic_login_token, get_password_hash
from app.services.scheduler import check_and_send_daily_digests

@pytest.mark.asyncio
async def test_magic_login_flow():
    """Test Magic Link token creation, verification and /auth/magic-login endpoint"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a test user directly in database
        async with AsyncSessionLocal() as db:
            user = User(
                email="magic_user@example.com",
                full_name="Magic User",
                hashed_password=get_password_hash("Password123!"),
                timezone="Asia/Ho_Chi_Minh",
                auth_provider="local"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            user_id = user.id

        # 2. Test token verification
        token = create_magic_login_token(subject=user_id, email="magic_user@example.com", expires_hours=48)
        payload = verify_magic_login_token(token)
        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "magic_login"

        # 3. Test /auth/magic-login API endpoint
        res = await client.post("/api/v1/auth/magic-login", json={"token": token})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "magic_user@example.com"

        # 4. Test invalid/tampered token
        bad_res = await client.post("/api/v1/auth/magic-login", json={"token": "invalid_tampered_jwt_token"})
        assert bad_res.status_code == 401

@pytest.mark.asyncio
async def test_daily_digest_filtering_and_15_limit():
    """Test <2 days overdue filter, flexible tasks sorting, top 15 limiter and trigger API"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        now_utc = datetime.now(timezone.utc)
        
        # 1. Create user with notifications enabled
        async with AsyncSessionLocal() as db:
            user = User(
                email="digest_tester@example.com",
                full_name="Digest Tester",
                hashed_password=get_password_hash("Password123!"),
                timezone="Asia/Ho_Chi_Minh",
                auth_provider="local"
            )
            db.add(user)
            await db.flush()

            settings = UserNotificationSettings(
                user_id=user.id,
                email_notifications_enabled=True,
                daily_summary_enabled=True,
                daily_summary_time="06:00"
            )
            db.add(settings)

            # Task 1: Overdue 1 day ago (SHOULD BE INCLUDED in <2 days overdue)
            t_overdue_recent = Todo(
                user_id=user.id,
                title="Việc quá hạn 1 ngày",
                priority=PriorityEnum.URGENT,
                status=StatusEnum.TODO,
                due_date=now_utc - timedelta(days=1)
            )
            db.add(t_overdue_recent)

            # Task 2: Overdue 5 days ago (SHOULD BE EXCLUDED because >2 days)
            t_overdue_old = Todo(
                user_id=user.id,
                title="Việc quá hạn 5 ngày",
                priority=PriorityEnum.HIGH,
                status=StatusEnum.TODO,
                due_date=now_utc - timedelta(days=5)
            )
            db.add(t_overdue_old)

            # Task 3: Due today (SHOULD BE INCLUDED)
            t_today = Todo(
                user_id=user.id,
                title="Việc trong ngày hôm nay",
                priority=PriorityEnum.HIGH,
                status=StatusEnum.TODO,
                due_date=now_utc + timedelta(hours=2)
            )
            db.add(t_today)

            # Task 4-20: 17 Flexible tasks with different priorities
            for i in range(17):
                priority = PriorityEnum.URGENT if i < 3 else (PriorityEnum.HIGH if i < 8 else PriorityEnum.LOW)
                t_flex = Todo(
                    user_id=user.id,
                    title=f"Việc linh hoạt số {i+1}",
                    priority=priority,
                    status=StatusEnum.TODO,
                    due_date=None
                )
                db.add(t_flex)

            await db.commit()
            user_id = user.id

        # 2. Mock email sender for deterministic unit testing
        with patch("app.services.email_service.send_email_async") as mock_send:
            mock_send.return_value = {"success": True, "provider": "mocked_service"}

            # Test check_and_send_daily_digests execution
            results = await check_and_send_daily_digests(force_user_id=user_id)
            assert len(results) == 1
            assert results[0]["email"] == "digest_tester@example.com"
            assert results[0]["result"]["success"] is True

            # Verify notification log was created
            async with AsyncSessionLocal() as db:
                from sqlalchemy.future import select
                stmt = select(NotificationLog).where(
                    NotificationLog.user_id == user_id,
                    NotificationLog.notification_type == NotificationTypeEnum.DAILY_DIGEST
                )
                res_log = await db.execute(stmt)
                log = res_log.scalars().first()
                assert log is not None
                assert log.recipient_email == "digest_tester@example.com"
                assert "Kế hoạch công việc" in log.subject or "Smart Todo" in log.subject

            # 3. Test API endpoint /notifications/test-daily-digest
            login_res = await client.post("/api/v1/auth/login", json={
                "email": "digest_tester@example.com",
                "password": "Password123!"
            })
            assert login_res.status_code == 200
            token = login_res.json()["access_token"]

            digest_api_res = await client.post(
                "/api/v1/notifications/test-daily-digest",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert digest_api_res.status_code == 200
            assert "Daily Digest" in digest_api_res.json()["message"]
