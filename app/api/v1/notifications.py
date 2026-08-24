from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.notification import (
    UserNotificationSettings, NotificationLog, NotificationTypeEnum, NotificationStatusEnum
)
from app.schemas.notification import (
    NotificationSettingsOut, NotificationSettingsUpdate,
    NotificationLogOut, TestEmailRequest
)
from app.services.email_service import send_test_email

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("/settings", response_model=NotificationSettingsOut)
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(UserNotificationSettings).where(UserNotificationSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    settings = result.scalars().first()

    if not settings:
        # Create default if missing
        settings = UserNotificationSettings(
            user_id=current_user.id,
            email_notifications_enabled=True,
            remind_before_minutes=30,
            daily_summary_enabled=True,
            daily_summary_time="08:00"
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings

@router.put("/settings", response_model=NotificationSettingsOut)
async def update_notification_settings(
    settings_in: NotificationSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(UserNotificationSettings).where(UserNotificationSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    settings = result.scalars().first()

    if not settings:
        settings = UserNotificationSettings(user_id=current_user.id)
        db.add(settings)

    if settings_in.email_notifications_enabled is not None:
        settings.email_notifications_enabled = settings_in.email_notifications_enabled
    if settings_in.remind_before_minutes is not None:
        settings.remind_before_minutes = settings_in.remind_before_minutes
    if settings_in.daily_summary_enabled is not None:
        settings.daily_summary_enabled = settings_in.daily_summary_enabled
    if settings_in.daily_summary_time is not None:
        settings.daily_summary_time = settings_in.daily_summary_time

    await db.commit()
    await db.refresh(settings)
    return settings

@router.get("/logs", response_model=List[NotificationLogOut])
async def get_notification_logs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(NotificationLog)
        .where(NotificationLog.user_id == current_user.id)
        .order_by(NotificationLog.sent_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return logs

@router.post("/test-email")
async def trigger_test_email(
    req: TestEmailRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    target_email = req.target_email if (req and req.target_email) else current_user.email
    res = await send_test_email(to_email=str(target_email), user_name=current_user.full_name)

    log_entry = NotificationLog(
        user_id=current_user.id,
        todo_id=None,
        notification_type=NotificationTypeEnum.TEST_EMAIL,
        status=NotificationStatusEnum.SENT if res.get("success") else NotificationStatusEnum.FAILED,
        recipient_email=str(target_email),
        subject="✅ [Smart Todo] Kiểm tra kết nối gửi email thành công",
        error_message=res.get("error") if not res.get("success") else None
    )
    db.add(log_entry)
    await db.commit()

    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi gửi email qua Resend: {res.get('error')}"
        )

    return {"message": f"Email thử nghiệm đã được gửi thành công đến {target_email}!"}
