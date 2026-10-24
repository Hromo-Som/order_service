from uuid import UUID

from src.domain.enums import OrderStatusEnum


class DomainError(Exception):
    """Базовое доменное исключение."""


class OrderNotFoundError(DomainError):
    """Заказ с указанным id не найден в хранилище."""

    def __init__(self, order_id: UUID) -> None:
        self.order_id = order_id
        super().__init__(f"Заказ {order_id} не найден.")


class ItemNotFoundError(DomainError):
    """Товар отсутствует в каталоге (404) или item_id невалиден (422 от Catalog)."""

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"Товар {item_id} не найден.")


class InsufficientStockError(DomainError):
    """Запрошенное количество превышает доступный остаток."""

    def __init__(self, item_id: str, requested: int, available: int) -> None:
        self.item_id = item_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Недопустимое количество для товара {item_id}: запрошено - {requested}, доступно - {available}."
        )


class InvalidOrderTransitionError(DomainError):
    """Попытка недопустимого перехода статуса заказа."""

    def __init__(
        self, order_id: UUID, current: OrderStatusEnum, target: OrderStatusEnum
    ) -> None:
        self.order_id = order_id
        self.current = current
        self.target = target
        super().__init__(
            f"Недопустимый переход заказа {order_id}: {current} → {target}."
        )


class PaymentCreationFailedError(DomainError):
    """Не удалось создать платёж в Payments Service."""

    def __init__(self, order_id: UUID, reason: str) -> None:
        self.order_id = order_id
        self.reason = reason
        super().__init__(f"Не удалось создать платёж для заказа {order_id}: {reason}")


class DuplicateIdempotencyKeyError(DomainError):
    """Заказ с таким idempotency_key уже существует."""

    def __init__(self, idempotency_key: str) -> None:
        self.idempotency_key = idempotency_key
        super().__init__(f"Заказ с idempotency_key={idempotency_key!r} уже существует")
