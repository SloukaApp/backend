from src.core.http_errors import HttpErrorResponse, map_error
from src.modules.auth.errors import (
    AuthorizationConflictError,
    ConfirmationConflictError,
    DeviceLimitError,
    DeviceNotFoundError,
    EmailUnconfirmedError,
    InvalidAccessError,
    InvalidConfirmationError,
    InvalidRefreshError,
    MailDeliveryError,
)

ERROR_MAPPINGS = (
    map_error(
        AuthorizationConflictError,
        HttpErrorResponse(409, "Authorization conflict; retry the operation"),
    ),
    map_error(
        InvalidAccessError,
        HttpErrorResponse(401, "Invalid or missing access token", {"WWW-Authenticate": "Bearer"}),
    ),
    map_error(InvalidRefreshError, HttpErrorResponse(401, "Invalid refresh token")),
    map_error(InvalidConfirmationError, HttpErrorResponse(401, "Invalid email confirmation")),
    map_error(EmailUnconfirmedError, HttpErrorResponse(403, "Email confirmation required")),
    map_error(DeviceLimitError, HttpErrorResponse(409, "Active device limit reached")),
    map_error(DeviceNotFoundError, HttpErrorResponse(404, "Device not found")),
    map_error(
        ConfirmationConflictError,
        HttpErrorResponse(409, "Confirmation cannot be resent yet or email is already confirmed"),
    ),
    map_error(
        MailDeliveryError,
        HttpErrorResponse(
            503,
            "Confirmation saved but email delivery failed; "
            "request a new confirmation after the cooldown",
        ),
    ),
)
