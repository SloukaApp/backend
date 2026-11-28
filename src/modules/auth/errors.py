from src.core.errors import ApplicationError


class InvalidAccessError(ApplicationError):
    pass


class InvalidRefreshError(ApplicationError):
    pass


class InvalidConfirmationError(ApplicationError):
    pass


class InvalidPasswordResetError(ApplicationError):
    pass


class EmailUnconfirmedError(ApplicationError):
    pass


class DeviceLimitError(ApplicationError):
    pass


class DeviceNotFoundError(ApplicationError):
    pass


class ConfirmationConflictError(ApplicationError):
    pass


class ConfirmationEnqueueError(ApplicationError):
    pass


class PasswordResetEnqueueError(ApplicationError):
    pass


class AuthorizationConflictError(ApplicationError):
    pass
