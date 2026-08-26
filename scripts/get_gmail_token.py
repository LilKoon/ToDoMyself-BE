#!/usr/bin/env python3
"""
Script hỗ trợ lấy GMAIL_REFRESH_TOKEN từ Google OAuth2 để gửi email qua Gmail REST API (Port 443 HTTPS).
Sử dụng: .venv/bin/python scripts/get_gmail_token.py
"""
import sys
import os
import urllib.parse
import httpx
import asyncio

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.config import settings

async def main():
    print("=" * 65)
    print("🚀 GOOGLE GMAIL REST API - CÔNG CỤ LẤY REFRESH TOKEN TỰ ĐỘNG")
    print("=" * 65)

    client_id = settings.GMAIL_CLIENT_ID or settings.GOOGLE_CLIENT_ID
    client_secret = settings.GMAIL_CLIENT_SECRET or settings.GOOGLE_CLIENT_SECRET

    if not client_id or not client_secret:
        print("\n⚠️ Không tìm thấy GOOGLE_CLIENT_ID hoặc GOOGLE_CLIENT_SECRET trong file .env!")
        client_id = input("👉 Nhập Google Client ID của bạn: ").strip()
        client_secret = input("👉 Nhập Google Client Secret của bạn: ").strip()

    redirect_uri = "https://developers.google.com/oauthplayground"
    scope = "https://www.googleapis.com/auth/gmail.send"

    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent"
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"

    print("\n📌 BƯỚC 1: Mở đường link dưới đây trên trình duyệt để ủy quyền tài khoản Gmail gửi email:")
    print("-" * 65)
    print(auth_url)
    print("-" * 65)
    print("\n📌 BƯỚC 2: Sau khi đăng nhập và bấm 'Tiếp tục / Cho phép', trình duyệt sẽ chuyển hướng đến trang Google OAuth Playground.")
    print("👉 Hãy nhìn vào ô 'Authorization code' bên trái, copy mã Authorization code (bắt đầu bằng 4/0A...) và dán vào đây.")
    print("-" * 65)

    auth_code = input("\n👉 Dán Authorization Code vào đây: ").strip()

    if not auth_code:
        print("❌ Authorization code không được để trống.")
        return

    # Exchange code for refresh token
    token_url = "https://oauth2.googleapis.com/token"
    token_payload = {
        "code": urllib.parse.unquote(auth_code),
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    print("\n⏳ Đang trao đổi Authorization Code lấy Refresh Token từ Google...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=token_payload)
        if resp.status_code == 200:
            data = resp.json()
            refresh_token = data.get("refresh_token")
            access_token = data.get("access_token")
            
            print("\n🎉 THÀNH CÔNG! ĐÃ LẤY ĐƯỢC REFRESH TOKEN TỪ GOOGLE:")
            print("=" * 65)
            print(f"GMAIL_REFRESH_TOKEN={refresh_token}")
            print("=" * 65)
            print("\n👉 Hãy copy dòng trên và dán vào:")
            print("  1. File .env trong thư mục ToDoMyself-BE")
            print("  2. Mục Variables trên Railway của bạn")
            print("  3. Thêm GMAIL_SENDER_EMAIL=email_clone_cua_ban@gmail.com")
        else:
            print(f"\n❌ Lỗi từ Google ({resp.status_code}): {resp.text}")

if __name__ == "__main__":
    asyncio.run(main())
