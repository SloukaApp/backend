from fastapi import Request, status
from fastapi.responses import JSONResponse

from src.core.http_errors import ExceptionHandlers, error_response
from src.modules.auth.errors import (
    AuthorizationConflictError,
    ConfirmationConflictError,
    ConfirmationEnqueueError,
    DeviceLimitError,
    DeviceNotFoundError,
    EmailUnconfirmedError,
    InvalidAccessError,
    InvalidConfirmationError,
    InvalidPasswordResetError,
    InvalidRefreshError,
    PasswordResetEnqueueError,
)


async def handle_authorization_conflict(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_409_CONFLICT, "Authorization conflict; retry the operation")


async def handle_invalid_access(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or missing access token",
        {"WWW-Authenticate": "Bearer"},
    )


async def handle_invalid_refresh(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")


async def handle_invalid_confirmation(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_401_UNAUTHORIZED, "Invalid email confirmation")


async def handle_invalid_password_reset(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_401_UNAUTHORIZED, "Invalid password reset code")


async def handle_password_reset_enqueue(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE, "Password reset temporarily unavailable"
    )


async def handle_email_unconfirmed(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_403_FORBIDDEN, "Email confirmation required")


async def handle_device_limit(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_409_CONFLICT, "Active device limit reached")


async def handle_device_not_found(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_404_NOT_FOUND, "Device not found")


async def handle_confirmation_conflict(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        status.HTTP_409_CONFLICT, "Confirmation cannot be resent yet or email is already confirmed"
    )


async def handle_confirmation_enqueue(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Confirmation saved but email could not be queued; "
        "request a new confirmation after the cooldown",
    )


EXCEPTION_HANDLERS: ExceptionHandlers = {
    AuthorizationConflictError: handle_authorization_conflict,
    ConfirmationConflictError: handle_confirmation_conflict,
    DeviceLimitError: handle_device_limit,
    DeviceNotFoundError: handle_device_not_found,
    EmailUnconfirmedError: handle_email_unconfirmed,
    InvalidAccessError: handle_invalid_access,
    InvalidConfirmationError: handle_invalid_confirmation,
    InvalidPasswordResetError: handle_invalid_password_reset,
    InvalidRefreshError: handle_invalid_refresh,
    ConfirmationEnqueueError: handle_confirmation_enqueue,
    PasswordResetEnqueueError: handle_password_reset_enqueue,
}
