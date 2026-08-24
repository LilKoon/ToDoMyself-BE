import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db, AsyncSessionLocal
from app.models.user import User
from app.models.todo import Todo, StatusEnum, PriorityEnum
from app.core.security import create_setup_token

@pytest.mark.asyncio
async def test_full_flow():
    await init_db()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test Health
        health_res = await client.get("/health")
        assert health_res.status_code == 200
        assert health_res.json() == {"status": "ok"}
        
        # 2. Test Register
        unique_email = f"testuser_{asyncio.get_event_loop().time()}@example.com"
        reg_res = await client.post("/api/v1/auth/register", json={
            "email": unique_email,
            "full_name": "Test User",
            "password": "Password123!",
            "timezone": "Asia/Ho_Chi_Minh"
        })
        assert reg_res.status_code == 201
        reg_data = reg_res.json()
        assert "access_token" in reg_data
        token = reg_data["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Test Get Me
        me_res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == unique_email
        assert me_data["has_password"] is True
        
        # 4. Test Create Todo with Subtasks
        todo_res = await client.post("/api/v1/todos", json={
            "title": "Học FastAPI và Next.js",
            "description": "Xây dựng ứng dụng Todo hoàn chỉnh",
            "priority": "HIGH",
            "status": "TODO",
            "category": "Study",
            "subtasks": [
                {"title": "Cài đặt backend FastAPI", "is_completed": True},
                {"title": "Xây dựng giao diện Next.js", "is_completed": False}
            ]
        }, headers=auth_headers)
        assert todo_res.status_code == 201
        todo_data = todo_res.json()
        assert todo_data["title"] == "Học FastAPI và Next.js"
        assert len(todo_data["subtasks"]) == 2
        todo_id = todo_data["id"]
        
        # 5. Test Update Status
        patch_res = await client.patch(f"/api/v1/todos/{todo_id}/status", json={
            "status": "IN_PROGRESS"
        }, headers=auth_headers)
        assert patch_res.status_code == 200
        assert patch_res.json()["status"] == "IN_PROGRESS"
        
        # 6. Test Stats Summary
        stats_res = await client.get("/api/v1/todos/stats/summary", headers=auth_headers)
        assert stats_res.status_code == 200
        stats_data = stats_res.json()
        assert stats_data["total_todos"] >= 1
        assert stats_data["in_progress_todos"] >= 1
        
        # 7. Test Notification Settings
        notif_res = await client.get("/api/v1/notifications/settings", headers=auth_headers)
        assert notif_res.status_code == 200
        notif_data = notif_res.json()
        assert notif_data["email_notifications_enabled"] is True
        assert notif_data["daily_summary_time"] == "08:00"
        
        # 8. Test Update Notification Settings
        update_notif_res = await client.put("/api/v1/notifications/settings", json={
            "daily_summary_time": "07:30",
            "remind_before_minutes": 60
        }, headers=auth_headers)
        assert update_notif_res.status_code == 200
        assert update_notif_res.json()["daily_summary_time"] == "07:30"
        assert update_notif_res.json()["remind_before_minutes"] == 60

        print("\nAll API integration tests PASSED successfully!")

if __name__ == "__main__":
    asyncio.run(test_full_flow())
