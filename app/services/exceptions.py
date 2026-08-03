class BookingServiceError(Exception):
    """Base class for all booking domain errors."""


class SeatNotFoundError(BookingServiceError):
    pass


class SeatAlreadyHeldError(BookingServiceError):
    """Raised when a seat's Redis lock is held by a different user."""


class SeatNotHeldByUserError(BookingServiceError):
    """Raised when a user tries to confirm/act on a seat they do not currently hold."""


class SeatAlreadyBookedError(BookingServiceError):
    pass
