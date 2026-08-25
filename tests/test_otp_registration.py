import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.future import select

from app.main import app
from app.core.database import init_db, AsyncSessionLocal
from app.models.otp import EmailOTP
from app.models.user import User

@pytest.mark.asyncio
async def test_otp_registration_flow_and_security():
    await init_db()
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        time_tag = asyncio.get_event_loop().time()
        test_email = f"otp_test_{time_tag}@example.com"
        test_name = "OTP Test User"
        test_pass = "SecurePass123!"

        # =========================================================================
        # 1. SEND OTP REQUEST
        # =========================================================================
        res_send = await client.post("/api/v1/auth/register/send-otp", json={
            "email": test_email,
            "full_name": test_name,
            "password": test_pass
        })
        assert res_send.status_code == 200
        data_send = res_send.json()
        assert "Mã OTP xác thực" in data_send["message"]
        assert data_send["cooldown_seconds"] == 60
        assert data_send["expires_in_seconds"] == 300

        # Verify OTP record in DB
        async with AsyncSessionLocal() as session:
            res_db = await session.execute(
                select(EmailOTP).where(EmailOTP.email == test_email).order_by(EmailOTP.created_at.desc())
            )
            otp_record = res_db.scalars().first()
            assert otp_record is not None
            assert len(otp_record.otp_code) == 6
            assert otp_record.is_used is False
            stored_otp = otp_record.otp_code

        # =========================================================================
        # 2. RATE LIMIT (COOLDOWN 60s)
        # =========================================================================
        res_fast_resend = await client.post("/api/v1/auth/register/send-otp", json={
            "email": test_email,
            "full_name": test_name,
            "password": test_pass
        })
        assert res_fast_resend.status_code == 429
        assert "Vui lòng đợi thêm" in res_fast_resend.json()["detail"]

        # =========================================================================
        # 3. WRONG OTP ATTEMPT
        # =========================================================================
        res_wrong_otp = await client.post("/api/v1/auth/register/verify-otp", json={
            "email": test_email,
            "otp_code": "000000"
        })
        assert res_wrong_otp.status_code == 400
        assert "Mã OTP không chính xác" in res_wrong_otp.json()["detail"]

        # =========================================================================
        # 4. EXPIRED OTP SIMULATION (> 5 MINUTES)
        # =========================================================================
        async with AsyncSessionLocal() as session:
            res_db = await session.execute(
                select(EmailOTP).where(EmailOTP.email == test_email).order_by(EmailOTP.created_at.desc())
            )
            otp_record = res_db.scalars().first()
            otp_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()

        res_expired = await client.post("/api/v1/auth/register/verify-otp", json={
            "email": test_email,
            "otp_code": stored_otp
        })
        assert res_expired.status_code == 400
        assert "Mã OTP đã hết hạn" in res_expired.json()["detail"]

        # =========================================================================
        # 5. RESEND OTP AFTER EXPIRY
        # =========================================================================
        # Reset last_sent_at to simulate 60s passed
        async with AsyncSessionLocal() as session:
            res_db = await session.execute(
                select(EmailOTP).where(EmailOTP.email == test_email).order_by(EmailOTP.created_at.desc())
            )
            otp_record = res_db.scalars().first()
            otp_record.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=70)
            await session.commit()

        res_resend = await client.post("/api/v1/auth/register/resend-otp", json={
            "email": test_email
        })
        assert res_resend.status_code == 200
        assert "Đã gửi lại mã OTP" in res_resend.json()["message"]

        # Get new OTP
        async with AsyncSessionLocal() as session:
            res_db = await session.execute(
                select(EmailOTP).where(EmailOTP.email == test_email).order_by(EmailOTP.created_at.desc())
            )
            new_otp_record = res_db.scalars().first()
            new_otp = new_otp_record.otp_code

        # =========================================================================
        # 6. VERIFY SUCCESS & USER CREATION
        # =========================================================================
        res_verify_success = await client.post("/api/v1/auth/register/verify-otp", json={
            "email": test_email,
            "otp_code": new_otp
        })
        assert res_verify_success.status_code == 201
        data_verified = res_verify_success.json()
        assert data_verified["access_token"] is not None
        assert data_verified["refresh_token"] is not None
        assert data_verified["user"]["email"] == test_email
        assert data_verified["user"]["full_name"] == test_name

        # Verify in DB that user exists and OTP is marked used
        async with AsyncSessionLocal() as session:
            res_user = await session.execute(select(User).where(User.email == test_email))
            created_user = res_user.scalars().first()
            assert created_user is not None
            assert created_user.email == test_email

            res_otp_used = await session.execute(
                select(EmailOTP).where(EmailOTP.email == test_email).order_by(EmailOTP.created_at.desc())
            )
            used_record = res_otp_used.scalars().first()
            assert used_record.is_used is True

        # =========================================================================
        # 7. CANNOT REUSE ALREADY USED OTP
        # =========================================================================
        res_reuse = await client.post("/api/v1/auth/register/verify-otp", json={
            "email": test_email,
            "otp_code": new_otp
        })
        assert res_reuse.status_code == 400
