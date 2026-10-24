from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    capashino_base_url: str = "https://capashino.dev-2.python-labs.ru"
    capashino_api_token: SecretStr = SecretStr("")

    kafka_bootstrap_servers: str = "kafka.kafka.svc.cluster.local:9092"
    payment_callback_url: str = (
        "http://order-service.order-service.svc:8000/api/orders/payment-callback"
    )

    postgres_connection_string: str | None = None
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/orders"

    @model_validator(mode="after")
    def _build_database_url(self) -> Settings:
        """Собрать database_url из postgres_connection_string, если не задан."""
        if self.postgres_connection_string:
            url = self.postgres_connection_string
            if url.startswith("postgres://"):
                url = "postgresql+asyncpg://" + url[len("postgres://") :]
            elif url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://") :]
            self.database_url = url
        return self

    @field_validator("payment_callback_url")
    @classmethod
    def _check_internal_callback(cls, v: str) -> str:
        """Запретить внешний домен в payment_callback_url."""
        if "python-labs.ru" in v and ".svc" not in v:
            raise ValueError(
                "payment_callback_url должен быть внутренним Kubernetes-адресом "
                "(http://<service>.<namespace>.svc:8000/...), а не внешним доменом"
            )
        return v
