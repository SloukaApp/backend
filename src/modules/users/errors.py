from src.core.errors import ApplicationError


class EmailAlreadyExistsError(ApplicationError):
    """The normalized email already belongs to an account."""


class InvalidCredentialsError(ApplicationError):
    """The email/password combination or current password is invalid."""


class UserNotFoundError(ApplicationError):
    """The account does not exist."""


class InvalidProfileError(ApplicationError):
    """The requested reminder configuration is incomplete."""


class InvalidPasswordError(ApplicationError):
    """The new password does not satisfy the minimum length."""
