import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import init_db

@pytest.mark.asyncio
async def test_todos_crud_and_multiuser_isolation():
    await init_db()
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        time_tag = asyncio.get_event_loop().time()

        # 1. Create User A
        res_a = await client.post("/api/v1/auth/register", json={
            "email": f"user_a_{time_tag}@example.com",
            "full_name": "User Alpha",
            "password": "PasswordAlpha123!",
            "timezone": "Asia/Ho_Chi_Minh"
        })
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # 2. Create User B
        res_b = await client.post("/api/v1/auth/register", json={
            "email": f"user_b_{time_tag}@example.com",
            "full_name": "User Beta",
            "password": "PasswordBeta123!",
            "timezone": "Asia/Ho_Chi_Minh"
        })
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 3. User A creates a Todo
        now = datetime.now(timezone.utc)
        todo_a_res = await client.post("/api/v1/todos", json={
            "title": "Báo cáo tài chính User A",
            "description": "Dữ liệu mật của User A",
            "priority": "URGENT",
            "status": "TODO",
            "category": "Finance",
            "due_date": (now + timedelta(minutes=30)).isoformat(),
            "subtasks": [
                {"title": "Tính toán doanh thu", "is_completed": False},
                {"title": "Ký biên bản", "is_completed": False}
            ]
        }, headers=headers_a)
        assert todo_a_res.status_code == 201
        todo_a_id = todo_a_res.json()["id"]
        subtask_a_id = todo_a_res.json()["subtasks"][0]["id"]


        # 4. ISOLATION CHECK: User B CANNOT read User A's todo
        get_other_res = await client.get(f"/api/v1/todos/{todo_a_id}", headers=headers_b)
        assert get_other_res.status_code == 404

        # 5. ISOLATION CHECK: User B CANNOT update User A's todo
        update_other_res = await client.put(f"/api/v1/todos/{todo_a_id}", json={
            "title": "Hacked Title"
        }, headers=headers_b)
        assert update_other_res.status_code == 404

        # 6. ISOLATION CHECK: User B CANNOT toggle User A's subtask
        toggle_other_sub_res = await client.patch(f"/api/v1/todos/subtasks/{subtask_a_id}", json={
            "is_completed": True
        }, headers=headers_b)
        assert toggle_other_sub_res.status_code == 404

        # 7. ISOLATION CHECK: User B CANNOT delete User A's todo
        delete_other_res = await client.delete(f"/api/v1/todos/{todo_a_id}", headers=headers_b)
        assert delete_other_res.status_code == 404

        # 8. User A updates their own todo and subtask
        toggle_sub_res = await client.patch(f"/api/v1/todos/subtasks/{subtask_a_id}", json={
            "is_completed": True
        }, headers=headers_a)
        assert toggle_sub_res.status_code == 200
        assert toggle_sub_res.json()["is_completed"] is True

        # 9. Test search filter
        search_res = await client.get("/api/v1/todos?search=tài+chính", headers=headers_a)
        assert search_res.status_code == 200
        assert len(search_res.json()) >= 1
        assert search_res.json()[0]["id"] == todo_a_id

        # 10. Test category filter
        cat_res = await client.get("/api/v1/todos?category=Finance", headers=headers_a)
        assert cat_res.status_code == 200
        assert len(cat_res.json()) >= 1

        # 11. Test priority filter
        prio_res = await client.get("/api/v1/todos?priority=URGENT", headers=headers_a)
        assert prio_res.status_code == 200
        assert len(prio_res.json()) >= 1

        # 12. Test date filter: today
        today_res = await client.get("/api/v1/todos?filter_type=today", headers=headers_a)
        assert today_res.status_code == 200
        assert len(today_res.json()) >= 1

        # 13. Complete task and verify completed filter
        comp_status_res = await client.patch(f"/api/v1/todos/{todo_a_id}/status", json={
            "status": "COMPLETED"
        }, headers=headers_a)
        assert comp_status_res.status_code == 200
        assert comp_status_res.json()["status"] == "COMPLETED"

        comp_filter_res = await client.get("/api/v1/todos?filter_type=completed", headers=headers_a)
        assert comp_filter_res.status_code == 200
        assert len(comp_filter_res.json()) >= 1

        # 14. Verify Stats accuracy for User A
        stats_a = await client.get("/api/v1/todos/stats/summary", headers=headers_a)
        assert stats_a.status_code == 200
        assert stats_a.json()["completed_todos"] == 1
        assert stats_a.json()["completion_rate"] == 100.0

        # User B should have 0 todos
        stats_b = await client.get("/api/v1/todos/stats/summary", headers=headers_b)
        assert stats_b.status_code == 200
        assert stats_b.json()["total_todos"] == 0
