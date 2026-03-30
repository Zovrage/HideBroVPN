from __future__ import annotations


class BusinessError(Exception):
    pass


class NotFoundError(BusinessError):
    pass


class AccessDeniedError(BusinessError):
    pass


class TrialAlreadyUsedError(BusinessError):
    pass


class PaymentPendingError(BusinessError):
    pass


class PaymentNotFoundError(BusinessError):
    pass


class RemnawaveAPIError(BusinessError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class PaymentGatewayError(BusinessError):
    pass
