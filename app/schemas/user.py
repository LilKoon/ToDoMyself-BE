from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    avatar_url: Optional[str] = None
    timezone: Optional[str] = "Asia/Ho_Chi_Minh"

class UserCreate(UserBase):
    password: str = Field(..., min_length=6, description="Mật khẩu tối thiểu 6 ký tự")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class GoogleAuthRequest(BaseModel):
    id_token: str

class SetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6, description="Mật khẩu mới tối thiểu 6 ký tự")
    setup_token: Optional[str] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None

class UserOut(UserBase):
    id: int
    auth_provider: str
    is_active: bool
    has_password: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    needs_password_setup: bool = False
    setup_token: Optional[str] = None
    user: Optional[UserOut] = None
    message: Optional[str] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str
