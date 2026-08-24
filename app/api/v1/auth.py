from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import jwt, JWTError

from app.core.database import get_db
from app.core.config import settings
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_setup_token,
    verify_setup_token,
    verify_google_token,
    get_current_user
)
from app.models.user import User
from app.models.notification import UserNotificationSettings
from app.schemas.user import (
    UserCreate, UserLogin, GoogleAuthRequest, SetPasswordRequest,
    UserUpdate, UserOut, TokenResponse, RefreshTokenRequest
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if email exists
    result = await db.execute(select(User).where(User.email == user_in.email.lower()))
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email đã được sử dụng. Vui lòng chọn email khác hoặc đăng nhập."
        )

    # Create new user
    new_user = User(
        email=user_in.email.lower(),
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        avatar_url=user_in.avatar_url,
        timezone=user_in.timezone or "Asia/Ho_Chi_Minh",
        auth_provider="local"
    )
    db.add(new_user)
    await db.flush()

    # Create default notification settings
    notif_settings = UserNotificationSettings(
        user_id=new_user.id,
        email_notifications_enabled=True,
        remind_before_minutes=30,
        daily_summary_enabled=True,
        daily_summary_time="08:00"
    )
    db.add(notif_settings)
    await db.commit()
    await db.refresh(new_user)

    access_token = create_access_token(new_user.id)
    refresh_token = create_refresh_token(new_user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        needs_password_setup=False,
        user=UserOut.model_validate(new_user),
        message="Đăng ký tài khoản thành công."
    )

@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == credentials.email.lower()))
    user = result.scalars().first()

    if not user or not user.hashed_password or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác."
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản đã bị vô hiệu hóa.")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        needs_password_setup=False,
        user=UserOut.model_validate(user),
        message="Đăng nhập thành công."
    )

@router.post("/google", response_model=TokenResponse)
async def google_auth(req: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    # Verify Google token
    id_info = verify_google_token(req.id_token)
    if not id_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google ID token không hợp lệ hoặc đã hết hạn."
        )

    email = id_info.get("email", "").lower()
    full_name = id_info.get("name", email.split("@")[0])
    avatar_url = id_info.get("picture")

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Không tìm thấy email trong tài khoản Google.")

    # Check if user exists
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        # First time login with Google -> create account without password
        user = User(
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            auth_provider="google",
            hashed_password=None # Must set password before full access!
        )
        db.add(user)
        await db.flush()

        notif_settings = UserNotificationSettings(
            user_id=user.id,
            email_notifications_enabled=True,
            remind_before_minutes=30,
            daily_summary_enabled=True,
            daily_summary_time="08:00"
        )
        db.add(notif_settings)
        await db.commit()
        await db.refresh(user)

    # RULE CHECK: If user does not have password set, block entry and require password setup!
    if not user.has_password:
        setup_token = create_setup_token(user.id, user.email)
        return TokenResponse(
            access_token=None,
            refresh_token=None,
            needs_password_setup=True,
            setup_token=setup_token,
            user=UserOut.model_validate(user),
            message="Đăng nhập Google thành công! Vui lòng thiết lập mật khẩu bảo vệ cho tài khoản của bạn để tiếp tục."
        )

    # User already has password set -> grant normal access
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        needs_password_setup=False,
        user=UserOut.model_validate(user),
        message="Đăng nhập Google thành công."
    )

@router.post("/set-password", response_model=TokenResponse)
async def set_password(
    req: SetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    user = None

    # Case 1: Setup via setup_token (First-time Google flow)
    if req.setup_token:
        payload = verify_setup_token(req.setup_token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token thiết lập mật khẩu không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại Google."
            )
        user_id = payload.get("sub")
        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalars().first()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng cung cấp setup_token để thiết lập mật khẩu."
        )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng.")

    # Update password
    user.hashed_password = get_password_hash(req.password)
    await db.commit()
    await db.refresh(user)

    # Issue access and refresh tokens now that password is set
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        needs_password_setup=False,
        setup_token=None,
        user=UserOut.model_validate(user),
        message="Thiết lập mật khẩu thành công! Chào mừng bạn đến với Smart Todo Hub."
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(req.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        token_type = payload.get("type")
        if not user_id or token_type != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token không hợp lệ.")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token đã hết hạn hoặc không hợp lệ.")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Người dùng không tồn tại hoặc đã bị khóa.")

    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        needs_password_setup=not user.has_password,
        user=UserOut.model_validate(user)
    )

@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/me", response_model=UserOut)
async def update_me(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    if user_update.avatar_url is not None:
        current_user.avatar_url = user_update.avatar_url
    if user_update.timezone is not None:
        current_user.timezone = user_update.timezone

    await db.commit()
    await db.refresh(current_user)
    return current_user
