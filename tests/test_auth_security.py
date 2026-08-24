import pytest
import asyncio
from datetime import timedelta
from httpx import AsyncClient, ASGITransport
from jose import jwt

from app.main import app
from app.core.config import settings
from app.core.database import init_db, AsyncSessionLocal
from app.models.user import User
from app.core.security import verify_password, get_password_hash, create_access_token

@pytest.mark.asyncio
async def test_auth_security_and_edge_cases():
    await init_db()
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        time_tag = asyncio.get_event_loop().time()
        test_email = f"security_user_{time_tag}@example.com"
        raw_password = "MySecurePassword123!"

        # 1. Register user
        reg_res = await client.post("/api/v1/auth/register", json={
            "email": test_email,
            "full_name": "Security Tester",
            "password": raw_password,
            "timezone": "Asia/Ho_Chi_Minh"
        })
        assert reg_res.status_code == 201
        reg_json = reg_res.json()
        assert "access_token" in reg_json
        assert "refresh_token" in reg_json
        access_token = reg_json["access_token"]
        refresh_token = reg_json["refresh_token"]

        # 2. Verify password is encrypted in database (Never plaintext)
        async with AsyncSessionLocal() as db:
            from sqlalchemy.future import select
            res = await db.execute(select(User).where(User.email == test_email))
            db_user = res.scalars().first()
            assert db_user is not None
            assert db_user.hashed_password != raw_password
            assert verify_password(raw_password, db_user.hashed_password) is True

        # 3. Duplicate Email Registration Rejection
        dup_res = await client.post("/api/v1/auth/register", json={
            "email": test_email,
            "full_name": "Duplicate Tester",
            "password": "OtherPassword123!"
        })
        assert dup_res.status_code == 400
        assert "Email đã được sử dụng" in dup_res.json()["detail"]

        # 4. Wrong Password Login Rejection
        wrong_login_res = await client.post("/api/v1/auth/login", json={
            "email": test_email,
            "password": "WrongPassword!"
        })
        assert wrong_login_res.status_code == 401

        # 5. Non-existent User Login Rejection
        ghost_login_res = await client.post("/api/v1/auth/login", json={
            "email": "ghost_user_does_not_exist@example.com",
            "password": "SomePassword123!"
        })
        assert ghost_login_res.status_code == 401

        # 6. Tampered / Invalid JWT Token Rejection
        tampered_token = access_token[:-5] + "XXXXX"
        bad_token_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
        assert bad_token_res.status_code == 401

        # 7. Expired JWT Token Rejection
        expired_token = create_access_token(db_user.id, expires_delta=timedelta(seconds=-10))
        expired_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert expired_res.status_code == 401

        # 8. Token Refresh Flow
        refresh_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh_res.status_code == 200
        new_access_token = refresh_res.json()["access_token"]
        assert new_access_token is not None

        # 9. Verify New Access Token Works
        me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access_token}"})
        assert me_res.status_code == 200
        assert me_res.json()["email"] == test_email

        # 10. Update Profile (Name & Timezone)
        update_res = await client.put("/api/v1/auth/me", json={
            "full_name": "Security Tester Updated",
            "timezone": "Asia/Tokyo"
        }, headers={"Authorization": f"Bearer {new_access_token}"})
        assert update_res.status_code == 200
        assert update_res.json()["full_name"] == "Security Tester Updated"
        assert update_res.json()["timezone"] == "Asia/Tokyo"
