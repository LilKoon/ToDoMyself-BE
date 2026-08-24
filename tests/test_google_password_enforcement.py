import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db, AsyncSessionLocal
from app.models.user import User
from app.core.security import create_setup_token

@pytest.mark.asyncio
async def test_google_first_time_password_enforcement():
    await init_db()
    
    unique_email = f"google_test_{asyncio.get_event_loop().time()}@gmail.com"
    user_id = None

    async with AsyncSessionLocal() as db:
        google_user = User(
            email=unique_email,
            full_name="Google Test User",
            auth_provider="google",
            hashed_password=None # Google first login: no password
        )
        db.add(google_user)
        await db.commit()
        await db.refresh(google_user)
        user_id = google_user.id

    assert user_id is not None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Attempt login with empty credentials should fail (401)
        login_res = await client.post("/api/v1/auth/login", json={
            "email": unique_email,
            "password": "randompassword"
        })
        assert login_res.status_code == 401
        
        # 2. Generate setup token for first-time password setting
        setup_token = create_setup_token(user_id, unique_email)

        # 3. Complete password setup using setup_token
        set_pwd_res = await client.post("/api/v1/auth/set-password", json={
            "password": "GoogleUserNewPassword123!",
            "setup_token": setup_token
        })
        assert set_pwd_res.status_code == 200
        data = set_pwd_res.json()
        assert data["needs_password_setup"] is False
        assert "access_token" in data
        assert data["access_token"] is not None
        
        # 4. Verify user now has password and can log in normally with new password
        login_after_res = await client.post("/api/v1/auth/login", json={
            "email": unique_email,
            "password": "GoogleUserNewPassword123!"
        })
        assert login_after_res.status_code == 200
        assert "access_token" in login_after_res.json()
