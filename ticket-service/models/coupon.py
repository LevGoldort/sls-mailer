"""Coupon model for ticket service"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from decimal import Decimal
import uuid


@dataclass
class Coupon:
    """Модель купона/промокода"""
    coupon_code: str
    discount_type: str  # "percentage" | "fixed_amount"
    discount_value: float
    event_ids: List[str]  # Список ID событий, к которым применим купон
    valid_from: Optional[str] = None  # ISO format: "2025-01-01T00:00:00Z" or None for permanent
    valid_until: Optional[str] = None  # ISO format: "2025-12-31T23:59:59Z" or None for permanent
    status: str = "active"  # "active" | "inactive" | "expired"
    max_uses: Optional[int] = None  # None = unlimited
    current_uses: int = 0
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def generate_code() -> str:
        """Генерирует уникальный код купона"""
        return f"YALLA{uuid.uuid4().hex[:8].upper()}"

    def to_dynamodb_item(self) -> Dict:
        """Конвертирует в формат DynamoDB"""
        item = {
            "PK": f"COUPON#{self.coupon_code}",
            "SK": "METADATA",
            "coupon_code": self.coupon_code,
            "discount_type": self.discount_type,
            "discount_value": Decimal(str(self.discount_value)),
            "event_ids": self.event_ids,
            "status": self.status,
            "current_uses": Decimal(str(self.current_uses)),
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            # GSI для поиска по статусу
            "GSI1PK": self.status,
        }

        # Добавляем даты только если они указаны
        if self.valid_from:
            item["valid_from"] = self.valid_from
        if self.valid_until:
            item["valid_until"] = self.valid_until
            item["GSI1SK"] = self.valid_until
        else:
            # Для постоянных купонов используем далекую дату для GSI
            item["GSI1SK"] = "9999-12-31T23:59:59Z"

        # Добавляем max_uses только если указан
        if self.max_uses is not None:
            item["max_uses"] = Decimal(str(self.max_uses))

        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Coupon':
        """Создает объект из DynamoDB item"""
        return cls(
            coupon_code=item["coupon_code"],
            discount_type=item["discount_type"],
            discount_value=float(item["discount_value"]),
            event_ids=item.get("event_ids", []),
            valid_from=item.get("valid_from"),
            valid_until=item.get("valid_until"),
            status=item.get("status", "active"),
            max_uses=int(item["max_uses"]) if item.get("max_uses") else None,
            current_uses=int(item.get("current_uses", 0)),
            description=item.get("description", ""),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at")
        )

    def is_valid(self, event_id: str, current_time: datetime = None) -> Tuple[bool, str]:
        """
        Проверяет валидность купона

        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        if current_time is None:
            from datetime import timezone
            current_time = datetime.now(timezone.utc)

        # Проверка статуса
        if self.status != "active":
            return False, "Купон неактивен"

        # Проверка применимости к событию
        if event_id not in self.event_ids:
            return False, "Купон не применим к этому событию"

        # Проверка даты действия (только если даты указаны)
        if self.valid_from:
            valid_from = datetime.fromisoformat(self.valid_from.replace('Z', '+00:00'))
            if current_time < valid_from:
                return False, "Купон еще не действует"

        if self.valid_until:
            valid_until = datetime.fromisoformat(self.valid_until.replace('Z', '+00:00'))
            if current_time > valid_until:
                return False, "Срок действия купона истек"

        # Проверка лимита использований
        if self.max_uses is not None and self.current_uses >= self.max_uses:
            return False, "Превышен лимит использований купона"

        return True, ""

    def calculate_discount(self, amount: float) -> float:
        """
        Рассчитывает сумму скидки

        Args:
            amount: Исходная сумма

        Returns:
            float: Сумма скидки
        """
        if self.discount_type == "percentage":
            discount = amount * (self.discount_value / 100)
        else:  # fixed_amount
            discount = min(self.discount_value, amount)

        return round(discount, 2)

    def apply_discount(self, amount: float) -> float:
        """
        Применяет скидку к сумме

        Args:
            amount: Исходная сумма

        Returns:
            float: Сумма со скидкой
        """
        discount = self.calculate_discount(amount)
        return round(max(0, amount - discount), 2)

    def increment_uses(self) -> None:
        """Увеличивает счетчик использований"""
        self.current_uses += 1
        self.updated_at = datetime.utcnow().isoformat()

        # Автоматически деактивируем если достигнут лимит
        if self.max_uses is not None and self.current_uses >= self.max_uses:
            self.status = "inactive"

    def can_be_used(self) -> bool:
        """Проверяет, может ли купон быть использован еще раз"""
        if self.status != "active":
            return False

        if self.max_uses is not None and self.current_uses >= self.max_uses:
            return False

        return True

    def get_discount_description(self) -> str:
        """Возвращает человекочитаемое описание скидки"""
        if self.discount_type == "percentage":
            return f"{self.discount_value}% скидка"
        else:
            return f"{self.discount_value}₪ скидка"

    def to_dict(self) -> Dict:
        """Конвертирует в словарь для API"""
        return asdict(self)
