class UpstreamServiceError(Exception):
    """Внешний сервис недоступен или вернул ошибку."""

    def __init__(self, service_name: str, reason: str) -> None:
        self.service_name = service_name
        self.reason = reason
        super().__init__(f"{service_name}: {reason}")
