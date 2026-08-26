import logging
import base64
import httpx
from datetime import datetime
from typing import List, Optional, Dict, Any
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
import aiosmtplib
import resend

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory access token cache for Gmail API (token, expires_at_timestamp)
_gmail_token_cache: Dict[str, Any] = {"access_token": None, "expires_at": 0}

async def get_gmail_access_token() -> Optional[str]:
    """Obtain a fresh OAuth2 access token for Gmail REST API from Google (caching for ~55 min)"""
    client_id = settings.GMAIL_CLIENT_ID or settings.GOOGLE_CLIENT_ID
    client_secret = settings.GMAIL_CLIENT_SECRET or settings.GOOGLE_CLIENT_SECRET
    refresh_token = settings.GMAIL_REFRESH_TOKEN

    if not (client_id and client_secret and refresh_token):
        return None

    now_ts = datetime.utcnow().timestamp()
    if _gmail_token_cache["access_token"] and _gmail_token_cache["expires_at"] > (now_ts + 60):
        return _gmail_token_cache["access_token"]

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": client_id.strip(),
        "client_secret": client_secret.strip(),
        "refresh_token": refresh_token.strip(),
        "grant_type": "refresh_token"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(token_url, data=payload)
            if resp.status_code == 200:
                data = resp.json()
                acc_token = data.get("access_token")
                expires_in = data.get("expires_in", 3500)
                _gmail_token_cache["access_token"] = acc_token
                _gmail_token_cache["expires_at"] = now_ts + expires_in
                logger.info("Successfully refreshed Google Gmail REST API OAuth2 access token.")
                return acc_token
            else:
                logger.error(f"Failed to refresh Gmail access token from Google: {resp.status_code} - {resp.text}")
                return None
    except Exception as e:
        logger.error(f"Error requesting Gmail access token: {e}")
        return None

async def send_via_gmail_api(to_email: str, subject: str, html_content: str) -> Dict[str, Any]:
    """Send email directly via official Google Gmail REST API (Port 443 HTTPS - Railway Compatible)"""
    access_token = await get_gmail_access_token()
    if not access_token:
        return {
            "success": False,
            "error": "Google OAuth2 refresh_token không hợp lệ hoặc thiếu GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN"
        }

    sender_email = settings.GMAIL_SENDER_EMAIL or settings.SMTP_USER or "me"
    from_header = settings.SMTP_FROM or formataddr(("Smart Todo Hub", sender_email))

    message = MIMEMultipart("alternative")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = from_header
    message["To"] = to_email

    html_part = MIMEText(html_content, "html", "utf-8")
    message.attach(html_part)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    send_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(send_url, json={"raw": raw_message}, headers=headers)
            if res.status_code in [200, 201]:
                res_data = res.json()
                logger.info(f"Email sent successfully via Google Gmail REST API (Port 443) to {to_email}: ID {res_data.get('id')}")
                return {"success": True, "provider": "gmail_api", "id": res_data.get("id")}
            else:
                err_text = f"Gmail REST API error ({res.status_code}): {res.text}"
                logger.error(err_text)
                return {"success": False, "error": err_text}
    except Exception as e:
        logger.error(f"Failed to connect to Google Gmail REST API: {e}")
        return {"success": False, "error": str(e)}

# Initialize Resend if key exists
if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY

def get_base_email_html(title: str, preheader: str, content_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 20px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
    .header {{ background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); padding: 32px 24px; text-align: center; color: #ffffff; }}
    .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; letter-spacing: -0.5px; }}
    .header p {{ margin: 6px 0 0 0; opacity: 0.9; font-size: 14px; }}
    .content {{ padding: 32px 24px; }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 18px; margin-bottom: 16px; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700; text-transform: uppercase; }}
    .badge-urgent {{ background: #fee2e2; color: #dc2626; }}
    .badge-high {{ background: #ffedd5; color: #ea580c; }}
    .badge-medium {{ background: #e0e7ff; color: #4338ca; }}
    .badge-low {{ background: #f1f5f9; color: #475569; }}
    .task-title {{ font-size: 16px; font-weight: 600; color: #0f172a; margin: 8px 0 4px 0; }}
    .task-desc {{ font-size: 13px; color: #64748b; margin: 0 0 8px 0; }}
    .meta {{ font-size: 12px; color: #94a3b8; display: flex; align-items: center; gap: 8px; }}
    .btn {{ display: inline-block; background: #4f46e5; color: #ffffff !important; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; text-align: center; margin-top: 16px; }}
    .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
    .section-title {{ font-size: 16px; font-weight: 700; color: #334155; margin: 20px 0 10px 0; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; }}
  </style>
</head>
<body>
  <div style="display:none;font-size:1px;color:#333333;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
    {preheader}
  </div>
  <div class="container">
    <div class="header">
      <h1>🚀 Smart Todo Hub</h1>
      <p>{title}</p>
    </div>
    <div class="content">
      {content_html}
    </div>
    <div class="footer">
      <p>Email này được gửi tự động từ hệ thống Smart Todo Hub theo cài đặt thông báo của bạn.</p>
      <p>© 2026 Smart Todo Hub. All rights reserved.</p>
    </div>
  </div>
</body>
</html>"""

async def send_email_async(to_email: str, subject: str, html_content: str) -> Dict[str, Any]:
    """Unified email dispatcher: Prioritizes Google Gmail REST API (HTTPS Port 443) -> SMTP -> Resend API -> Console Fallback"""
    # 1. Priority 1: Google Gmail REST API via HTTPS (Port 443 - Perfect for Cloud / Railway)
    if settings.GMAIL_REFRESH_TOKEN:
        logger.info(f"Attempting to send email via Google Gmail REST API (HTTPS Port 443) to {to_email}...")
        gmail_res = await send_via_gmail_api(to_email, subject, html_content)
        if gmail_res.get("success"):
            return gmail_res
        logger.warning(f"Google Gmail REST API failed: {gmail_res.get('error')}. Falling back to secondary providers...")

    # 2. Priority 2: Standard SMTP (Gmail Port 465 SSL/587)
    smtp_errors = []
    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        from_addr = settings.SMTP_FROM or formataddr(("Smart Todo Hub", settings.SMTP_USER.strip()))
        
        message = MIMEMultipart("alternative")
        message["Subject"] = Header(subject, "utf-8")
        message["From"] = from_addr
        message["To"] = to_email
        
        html_part = MIMEText(html_content, "html", "utf-8")
        message.attach(html_part)

        clean_password = settings.SMTP_PASSWORD.replace(" ", "").strip()
        clean_user = settings.SMTP_USER.strip()

        primary_port = int(settings.SMTP_PORT)
        alt_port = 587 if primary_port == 465 else 465
        ports_to_try = [primary_port, alt_port]

        for port in ports_to_try:
            use_direct_ssl = (port == 465)
            try:
                logger.info(f"Attempting to send email via SMTP ({clean_user}) on port {port} (use_tls={use_direct_ssl})...")
                await aiosmtplib.send(
                    message,
                    hostname=settings.SMTP_HOST,
                    port=port,
                    use_tls=use_direct_ssl,
                    start_tls=not use_direct_ssl,
                    username=clean_user,
                    password=clean_password,
                    timeout=8
                )
                logger.info(f"Email sent successfully via SMTP on port {port} to {to_email}")
                return {"success": True, "provider": "smtp", "port": port}
            except Exception as e:
                err_msg = f"Port {port} failed: {e}"
                logger.warning(f"SMTP error on port {port}: {e}")
                smtp_errors.append(err_msg)

    # 3. Priority 3: Send via Resend SDK
    if settings.RESEND_API_KEY:
        try:
            params = {
                "from": settings.EMAIL_FROM,
                "to": [to_email],
                "subject": subject,
                "html": html_content
            }
            response = resend.Emails.send(params)
            logger.info(f"Email sent successfully via Resend API to {to_email}: {response}")
            return {"success": True, "provider": "resend", "response": response}
        except Exception as e:
            resend_err = str(e)
            logger.error(f"Failed to send email via Resend to {to_email}: {resend_err}")
            combined_err = f"SMTP errors: {'; '.join(smtp_errors)} | Resend error: {resend_err}" if smtp_errors else resend_err
            return {"success": False, "error": combined_err}

    # 4. Fallback: Dev console log if all failed or not configured
    if smtp_errors:
        return {"success": False, "error": f"SMTP failed on all ports: {'; '.join(smtp_errors)}"}

    logger.warning(f"No active email provider configured. [DEV EMAIL] To: {to_email} | Subject: {subject}")
    return {"success": True, "provider": "dev_console_log"}



async def send_task_reminder_email(
    to_email: str,
    user_name: str,
    todo: Dict[str, Any]
) -> Dict[str, Any]:
    """Send task reminder email before deadline or at scheduled reminder_time"""
    title = f"⏰ Nhắc nhở: {todo['title']}"
    preheader = f"Bạn có công việc cần làm: {todo['title']} - Mức độ ưu tiên: {todo.get('priority', 'Trung bình')}"
    
    priority_badges = {
        "URGENT": '<span class="badge badge-urgent">Khẩn Cấp</span>',
        "HIGH": '<span class="badge badge-high">Quan Trọng</span>',
        "MEDIUM": '<span class="badge badge-medium">Trung Bình</span>',
        "LOW": '<span class="badge badge-low">Thấp</span>',
    }
    badge = priority_badges.get(todo.get("priority", "MEDIUM"), "")
    
    due_str = "Không đặt hạn"
    if todo.get("due_date"):
        try:
            dt = datetime.fromisoformat(todo["due_date"].replace("Z", "+00:00"))
            due_str = dt.strftime("%H:%M • %d/%m/%Y")
        except Exception:
            due_str = str(todo["due_date"])

    subtasks_html = ""
    if todo.get("subtasks"):
        st_items = "".join([
            f'<li style="margin: 6px 0; font-size: 13px; color: {"#94a3b8; text-decoration: line-through;" if s.get("is_completed") else "#334155;"}">{"✅" if s.get("is_completed") else "⬜"} {s["title"]}</li>'
            for s in todo["subtasks"]
        ])
        subtasks_html = f"""
        <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed #cbd5e1;">
          <p style="font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; margin: 0 0 6px 0;">Danh sách việc con:</p>
          <ul style="padding-left: 20px; margin: 0;">{st_items}</ul>
        </div>
        """

    content_html = f"""
    <p style="font-size: 15px; margin-top: 0;">Xin chào <strong>{user_name}</strong>,</p>
    <p style="font-size: 14px; color: #475569;">Đây là email nhắc nhở tự động từ hệ thống Smart Todo Hub về công việc sắp tới hạn của bạn:</p>
    
    <div class="card" style="border-left: 4px solid #6366f1;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-size: 12px; color: #64748b; font-weight: 600;">📁 {todo.get('category', 'General')}</span>
        {badge}
      </div>
      <div class="task-title" style="font-size: 18px; color: #1e1b4b;">{todo['title']}</div>
      <div class="task-desc">{todo.get('description') or 'Không có mô tả chi tiết.'}</div>
      <div class="meta" style="margin-top: 12px; padding-top: 10px; border-top: 1px solid #f1f5f9;">
        <span>📅 Hạn hoàn thành: <strong style="color: #0f172a;">{due_str}</strong></span>
      </div>
      {subtasks_html}
    </div>
    
    <div style="text-align: center; margin-top: 24px;">
      <a href="http://localhost:3000/dashboard" class="btn">Mở Bảng Công Việc Để Cập Nhật</a>
    </div>
    """

    html_content = get_base_email_html(title, preheader, content_html)
    subject = f"⏰ [Smart Todo] Nhắc nhở công việc: {todo['title']}"
    return await send_email_async(to_email, subject, html_content)

async def send_daily_digest_email(
    to_email: str,
    user_name: str,
    overdue_tasks: List[Dict[str, Any]],
    today_tasks: List[Dict[str, Any]],
    upcoming_24h_tasks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Send morning daily digest summary email"""
    title = "🌅 Kế Hoạch Công Việc Trong Ngày"
    preheader = f"Hôm nay bạn có {len(today_tasks)} việc cần làm, {len(overdue_tasks)} việc quá hạn, {len(upcoming_24h_tasks)} việc sắp đến."

    def render_task_card(t: Dict[str, Any], border_color: str) -> str:
        due_str = ""
        if t.get("due_date"):
            try:
                dt = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                due_str = dt.strftime("%H:%M • %d/%m")
            except Exception:
                due_str = str(t["due_date"])
        return f"""
        <div class="card" style="border-left: 4px solid {border_color}; padding: 12px 16px; margin-bottom: 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong style="font-size: 14px; color: #1e293b;">{t['title']}</strong>
            <span style="font-size: 11px; color: #64748b;">📁 {t.get('category', 'General')}</span>
          </div>
          {f'<div style="font-size: 12px; color: #64748b; margin-top: 4px;">⏰ {due_str}</div>' if due_str else ''}
        </div>
        """

    sections_html = ""
    if overdue_tasks:
        cards = "".join([render_task_card(t, "#ef4444") for t in overdue_tasks])
        sections_html += f"""
        <div class="section-title" style="color: #dc2626;">
          🔴 Việc quá hạn cần xử lý gấp ({len(overdue_tasks)})
        </div>
        {cards}
        """

    if today_tasks:
        cards = "".join([render_task_card(t, "#6366f1") for t in today_tasks])
        sections_html += f"""
        <div class="section-title" style="color: #4f46e5;">
          🔵 Việc cần hoàn thành hôm nay ({len(today_tasks)})
        </div>
        {cards}
        """

    if upcoming_24h_tasks:
        cards = "".join([render_task_card(t, "#f59e0b") for t in upcoming_24h_tasks])
        sections_html += f"""
        <div class="section-title" style="color: #d97706;">
          ⏳ Sắp đến hạn trong 24h tới ({len(upcoming_24h_tasks)})
        </div>
        {cards}
        """

    if not (overdue_tasks or today_tasks or upcoming_24h_tasks):
        sections_html = """
        <div style="text-align:center; padding: 24px; background:#f0fdf4; border-radius:12px; border: 1px solid #bbf7d0;">
          <p style="font-size: 16px; color: #166534; font-weight:600; margin:0;">🎉 Tuyệt vời! Bạn không có công việc nào tồn đọng hoặc sắp đến hạn.</p>
          <p style="font-size: 13px; color: #15803d; margin: 6px 0 0 0;">Hãy tận hưởng ngày làm việc hiệu quả hoặc thêm mục tiêu mới vào bảng việc.</p>
        </div>
        """

    content_html = f"""
    <p style="font-size: 15px; margin-top: 0;">Chào buổi sáng <strong>{user_name}</strong>,</p>
    <p style="font-size: 14px; color: #475569;">Dưới đây là tổng hợp các công việc cần chú ý của bạn theo thời gian:</p>
    
    {sections_html}
    
    <div style="text-align: center; margin-top: 28px;">
      <a href="http://localhost:3000/dashboard" class="btn">Mở Bảng Công Việc (Todo Dashboard)</a>
    </div>
    """

    html_content = get_base_email_html(title, preheader, content_html)
    subject = f"🌅 [Smart Todo] Kế hoạch công việc hôm nay của bạn ({len(overdue_tasks) + len(today_tasks) + len(upcoming_24h_tasks)} việc)"
    return await send_email_async(to_email, subject, html_content)

async def send_test_email(to_email: str, user_name: str) -> Dict[str, Any]:
    """Send test email to verify email server setup"""
    title = "✅ Kiểm Tra Kết Nối Email Thành Công!"
    preheader = "Hệ thống thông báo Smart Todo Hub đã kết nối thành công với hòm thư của bạn."
    
    content_html = f"""
    <p style="font-size: 15px; margin-top: 0;">Xin chào <strong>{user_name}</strong>,</p>
    <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 12px; padding: 20px; text-align: center; margin: 16px 0;">
      <div style="font-size: 36px; margin-bottom: 8px;">🎉</div>
      <h3 style="margin: 0 0 8px 0; color: #065f46; font-size: 18px;">Kết Nối Email Hoàn Tất!</h3>
      <p style="margin: 0; color: #047857; font-size: 14px;">
        Hệ thống gửi thông báo tự động đã hoạt động hoàn hảo.
      </p>
    </div>
    <p style="font-size: 14px; color: #475569;">
      Từ bây giờ, bạn sẽ nhận được thông báo nhắc việc theo đúng cài đặt giờ giấc và múi giờ cá nhân của mình.
    </p>
    """
    
    html_content = get_base_email_html(title, preheader, content_html)
    subject = "✅ [Smart Todo] Kiểm tra kết nối gửi email thành công"
    return await send_email_async(to_email, subject, html_content)

async def send_otp_registration_email(to_email: str, user_name: str, otp_code: str) -> Dict[str, Any]:
    """Send 6-digit OTP email for new user registration verification (valid for 5 minutes)"""
    title = f"🔐 Mã xác thực đăng ký tài khoản của bạn: {otp_code}"
    preheader = f"Mã xác thực OTP của bạn là {otp_code}. Mã có hiệu lực trong 5 phút."
    
    content_html = f"""
    <p style="font-size: 15px; margin-top: 0;">Xin chào <strong>{user_name}</strong>,</p>
    <p style="font-size: 14px; color: #475569;">
      Cảm ơn bạn đã đăng ký tài khoản tại <strong>Smart Todo Hub</strong>. Để hoàn tất quy trình tạo tài khoản, vui lòng nhập mã xác thực OTP 6 chữ số bên dưới:
    </p>
    
    <div style="background: linear-gradient(135deg, #eef2ff 0%, #ede9fe 100%); border: 2px dashed #6366f1; border-radius: 16px; padding: 24px; text-align: center; margin: 24px 0;">
      <p style="margin: 0 0 8px 0; color: #4f46e5; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">MÃ XÁC THỰC CỦA BẠN</p>
      <div style="font-size: 38px; font-weight: 900; letter-spacing: 8px; color: #312e81; font-family: monospace; padding: 8px 0;">
        {otp_code}
      </div>
      <p style="margin: 8px 0 0 0; color: #6b7280; font-size: 12px;">
        ⏳ Mã này có hiệu lực trong vòng <strong>5 phút</strong>
      </p>
    </div>
    
    <div style="background: #fffbeb; border: 1px solid #fde68a; border-radius: 12px; padding: 14px 16px; font-size: 13px; color: #92400e; margin-bottom: 20px;">
      ⚠️ <strong>Lưu ý bảo mật:</strong> Tuyệt đối không chia sẻ mã này cho bất kỳ ai. Nhân viên Smart Todo Hub sẽ không bao giờ yêu cầu cung cấp mã OTP của bạn.
    </div>
    """
    
    html_content = get_base_email_html("Xác Thực Tài Khoản Smart Todo Hub", preheader, content_html)
    subject = f"🔐 [Smart Todo] Mã xác thực OTP đăng ký tài khoản ({otp_code})"
    return await send_email_async(to_email, subject, html_content)
