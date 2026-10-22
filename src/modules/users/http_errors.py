from src.core.http_errors import HttpErrorResponse, map_error
from src.modules.users.errors import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidProfileError,
    UserNotFoundError,
)

ERROR_MAPPINGS = (
    map_error(InvalidPasswordError, HttpErrorResponse(422, "Invalid password")),
    map_error(EmailAlreadyExistsError, HttpErrorResponse(409, "Email already registered")),
    map_error(InvalidCredentialsError, HttpErrorResponse(401, "Invalid credentials")),
    map_error(UserNotFoundError, HttpErrorResponse(401, "Account unavailable")),
    map_error(InvalidProfileError, HttpErrorResponse(422, "Invalid reminder settings")),
)
