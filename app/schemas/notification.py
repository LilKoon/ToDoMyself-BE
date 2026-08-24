from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.notification import NotificationTypeEnum, NotificationStatusEnum

class NotificationSettingsBase(BaseModel):
    email_notifications_enabled: bool = True
    remind_before_minutes: int = Field(default=30, ge=5, le=1440)
    daily_summary_enabled: bool = True
    daily_summary_time: str = Field(default="08:00", pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")

class NotificationSettingsUpdate(BaseModel):
    email_notifications_enabled: Optional[bool] = None
    remind_before_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    daily_summary_enabled: Optional[bool] = None
    daily_summary_time: Optional[str] = Field(default=None, pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")

class NotificationSettingsOut(NotificationSettingsBase):
    id: int
    user_id: int
    last_daily_digest_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class NotificationLogOut(BaseModel):
    id: int
    user_id: int
    todo_id: Optional[int] = None
    notification_type: NotificationTypeEnum
    status: NotificationStatusEnum
    recipient_email: str
    subject: str
    error_message: Optional[str] = None
    sent_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TestEmailRequest(BaseModel):
    target_email: Optional[EmailStr] = None
