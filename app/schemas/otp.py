from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class SendOTPRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=6)

class ResendOTPRequest(BaseModel):
    email: EmailStr

class OTPResponse(BaseModel):
    message: str
    cooldown_seconds: int = 60
    expires_in_seconds: int = 300
