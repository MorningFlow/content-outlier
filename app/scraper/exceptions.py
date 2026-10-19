class ScraperException(Exception):
    """Base exception for Instagram scraping errors."""
    pass


class ProfileNotFoundException(ScraperException):
    """Raised when an Instagram profile does not exist."""
    pass


class PrivateProfileException(ScraperException):
    """Raised when an Instagram profile is private and cannot be read without following."""
    pass


class RateLimitException(ScraperException):
    """Raised when Instagram sends a 429 Too Many Requests or query throttle."""
    def __init__(self, message: str, retry_after_seconds: int = 3600):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class CheckpointException(ScraperException):
    """Raised when Instagram requires a checkpoint / challenge verification."""
    pass


class InstagramAuthException(ScraperException):
    """Raised when authentication credentials or session files are invalid."""
    pass
