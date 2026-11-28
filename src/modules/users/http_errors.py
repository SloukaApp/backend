from fastapi import Request, status
from fastapi.responses import JSONResponse

from src.core.http_errors import ExceptionHandlers, error_response
from src.modules.users.errors import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidProfileError,
    UserNotFoundError,
)


async def handle_invalid_password(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid password")


async def handle_email_already_exists(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_409_CONFLICT, "Email already registered")


async def handle_invalid_credentials(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")


async def handle_user_not_found(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_401_UNAUTHORIZED, "Account unavailable")


async def handle_invalid_profile(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid reminder settings")


EXCEPTION_HANDLERS: ExceptionHandlers = {
    EmailAlreadyExistsError: handle_email_already_exists,
    InvalidCredentialsError: handle_invalid_credentials,
    InvalidPasswordError: handle_invalid_password,
    InvalidProfileError: handle_invalid_profile,
    UserNotFoundError: handle_user_not_found,
}
