import resend
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Initialize Resend
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

def get_priority_badge(priority: str) -> str:
    p = priority.upper() if priority else "MEDIUM"
    css_class = {
        "URGENT": "badge-urgent",
        "HIGH": "badge-high",
        "MEDIUM": "badge-medium",
        "LOW": "badge-low"
    }.get(p, "badge-medium")
    return f'<span class="badge {css_class}">{p}</span>'

async def send_task_reminder_email(
    to_email: str,
    user_name: str,
    todo: Dict[str, Any]
) -> Dict[str, Any]:
    """Send single task reminder email"""
    title = f"⏰ Nhắc nhở công việc: {todo.get('title')}"
    preheader = f"Bạn có công việc cần làm: {todo.get('title')}"
    
    due_str = "Không có hạn"
    if todo.get("due_date"):
        try:
            if isinstance(todo["due_date"], str):
                dt = datetime.fromisoformat(todo["due_date"])
            else:
                dt = todo["due_date"]
            due_str = dt.strftime("%H:%M ngày %d/%m/%Y")
        except Exception:
            due_str = str(todo.get("due_date"))

    subtasks_html = ""
    subtasks = todo.get("subtasks", [])
    if subtasks:
        items = "".join([f"<li style='margin-bottom:4px; {'text-decoration:line-through;color:#94a3b8;' if s.get('is_completed') else ''}'>{s.get('title')}</li>" for s in subtasks])
        subtasks_html = f"""
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px dashed #cbd5e1;">
          <strong style="font-size: 13px; color: #475569;">Danh sách việc con:</strong>
          <ul style="margin: 6px 0 0 0; padding-left: 20px; font-size: 13px;">
            {items}
          </ul>
        </div>
        """

    content_html = f"""
    <p style="font-size: 15px; margin-top: 0;">Xin chào <strong>{user_name}</strong>,</p>
    <p style="font-size: 14px; color: #475569;">Đây là thông báo nhắc nhở về công việc đã đến giờ thực hiện của bạn:</p>
    
    <div class="card" style="border-left: 4px solid #6366f1;">
      {get_priority_badge(todo.get('priority', 'MEDIUM'))}
      <div class="task-title">{todo.get('title')}</div>
      {f'<p class="task-desc">{todo.get("description")}</p>' if todo.get("description") else ''}
      <div class="meta">
        <span>📅 Hạn chót: <strong>{due_str}</strong></span>
        <span>🏷️ Danh mục: <strong>{todo.get('category', 'General')}</strong></span>
      </div>
      {subtasks_html}
    </div>
    
    <div style="text-align: center; margin-top: 24px;">
      <a href="http://localhost:3000/dashboard" class="btn">Mở Todo Dashboard & Hoàn Thành</a>
    </div>
    """

    html_content = get_base_email_html(title, preheader, content_html)

    try:
        params = {
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": title,
            "html": html_content
        }
        response = resend.Emails.send(params)
        logger.info(f"Task reminder email sent to {to_email}: {response}")
        return {"success": True, "response": response}
    except Exception as e:
        logger.error(f"Failed to send task reminder email to {to_email}: {e}")
        return {"success": False, "error": str(e)}

async def send_daily_digest_email(
    to_email: str,
    user_name: str,
    overdue_tasks: List[Dict[str, Any]],
    today_tasks: List[Dict[str, Any]],
    upcoming_24h_tasks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Send daily digest email based on user's custom schedule.
    Rules:
    1. Overdue incomplete tasks.
    2. Today's tasks.
    3. Upcoming tasks within 1 day (due <= 24h).
    Tasks > 1 day away are NOT included until they are within 1 day.
    """
    title = "🌅 Kế hoạch & Danh sách công việc hôm nay của bạn"
    preheader = f"Bạn có {len(overdue_tasks) + len(today_tasks) + len(upcoming_24h_tasks)} công việc cần lưu ý hôm nay."

    def render_task_card(t: Dict[str, Any], border_color: str) -> str:
        due_str = ""
        if t.get("due_date"):
            try:
                dt = datetime.fromisoformat(t["due_date"]) if isinstance(t["due_date"], str) else t["due_date"]
                due_str = f" • Hạn: {dt.strftime('%H:%M %d/%m')}"
            except Exception:
                due_str = f" • Hạn: {t.get('due_date')}"

        return f"""
        <div class="card" style="border-left: 4px solid {border_color}; margin-bottom: 10px; padding: 12px 16px;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
            <div style="font-weight: 600; font-size: 14px; color: #1e293b;">{t.get('title')}</div>
            {get_priority_badge(t.get('priority', 'MEDIUM'))}
          </div>
          <div style="font-size: 12px; color: #64748b; margin-top: 4px;">
            📁 {t.get('category', 'General')}{due_str}
          </div>
        </div>
        """

    sections_html = ""

    if overdue_tasks:
        cards = "".join([render_task_card(t, "#ef4444") for t in overdue_tasks])
        sections_html += f"""
        <div class="section-title" style="color: #dc2626;">
          ⚠️ Việc chưa hoàn thành & Quá hạn ({len(overdue_tasks)})
        </div>
        {cards}
        """

    if today_tasks:
        cards = "".join([render_task_card(t, "#3b82f6") for t in today_tasks])
        sections_html += f"""
        <div class="section-title" style="color: #2563eb;">
          📌 Việc cần làm hôm nay ({len(today_tasks)})
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

    try:
        params = {
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": f"🌅 [Smart Todo] Kế hoạch công việc hôm nay của bạn ({len(overdue_tasks) + len(today_tasks) + len(upcoming_24h_tasks)} việc)",
            "html": html_content
        }
        response = resend.Emails.send(params)
        logger.info(f"Daily digest email sent to {to_email}: {response}")
        return {"success": True, "response": response}
    except Exception as e:
        logger.error(f"Failed to send daily digest email to {to_email}: {e}")
        return {"success": False, "error": str(e)}

async def send_test_email(to_email: str, user_name: str) -> Dict[str, Any]:
    """Send test email to verify Resend setup"""
    title = "✅ Kiểm Tra Kết Nối Email Thành Công!"
    preheader = "Hệ thống thông báo Smart Todo Hub đã kết nối thành công với hòm thư của bạn."
    
    content_html = f"""
    <p style="font-size: 15px; margin-top: 0;">Xin chào <strong>{user_name}</strong>,</p>
    <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 12px; padding: 20px; text-align: center; margin: 16px 0;">
      <div style="font-size: 36px; margin-bottom: 8px;">🎉</div>
      <h3 style="margin: 0 0 8px 0; color: #065f46; font-size: 18px;">Kết Nối Email Hoàn Tất!</h3>
      <p style="margin: 0; color: #047857; font-size: 14px;">
        Hệ thống gửi thông báo tự động qua <strong>Resend API</strong> đã hoạt động hoàn hảo.
      </p>
    </div>
    <p style="font-size: 14px; color: #475569;">
      Từ bây giờ, bạn sẽ nhận được thông báo nhắc việc theo đúng cài đặt giờ giấc và múi giờ cá nhân của mình.
    </p>
    """
    
    html_content = get_base_email_html(title, preheader, content_html)
    
    try:
        params = {
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": "✅ [Smart Todo] Kiểm tra kết nối gửi email thành công",
            "html": html_content
        }
        response = resend.Emails.send(params)
        logger.info(f"Test email sent to {to_email}: {response}")
        return {"success": True, "response": response}
    except Exception as e:
        logger.error(f"Failed to send test email to {to_email}: {e}")
        return {"success": False, "error": str(e)}

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
    
    try:
        params = {
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": f"🔐 [Smart Todo] Mã xác thực OTP đăng ký tài khoản ({otp_code})",
            "html": html_content
        }
        response = resend.Emails.send(params)
        logger.info(f"Registration OTP email sent to {to_email}: {response}")
        return {"success": True, "response": response}
    except Exception as e:
        logger.error(f"Failed to send OTP email to {to_email}: {e}")
        return {"success": False, "error": str(e)}

