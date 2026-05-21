"""Event model for ticket service"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from datetime import datetime
import uuid


@dataclass
class TicketType:
    """Тип билета (Regular, VIP, etc)"""
    id: str
    name: str
    price: float
    total: int
    available: int

    def to_dict(self):
        return asdict(self)


@dataclass
class Recurrence:
    """Настройки повторяющегося события"""
    enabled: bool = False
    pattern: Optional[str] = None  # "weekly" | "monthly"
    interval: int = 1
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    end_date: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class RefundPolicy:
    """Политика возврата"""
    enabled: bool = True
    hours_before: int = 48

    def to_dict(self):
        return asdict(self)


@dataclass
class Event:
    """Модель события"""
    event_id: str
    title: str
    description: str
    date: str  # ISO format: "2025-01-15T19:00:00Z"
    location_id: str
    ticket_types: List[TicketType]
    currency: str = "ILS"
    images: List[str] = field(default_factory=list)
    status: str = "active"  # "active" | "sold_out" | "cancelled"
    recurrence: Optional[Recurrence] = None
    refund_policy: RefundPolicy = field(default_factory=lambda: RefundPolicy())
    slug: Optional[str] = None  # Короткий URL /events/<slug>.html
    seat_allocation: Optional[Dict[str, str]] = None  # {"0-5": "tt-xxx", ...} - распределение мест по типам билетов
    owner_id: Optional[str] = None   # user_id владельца; None для событий до миграции
    tenant_id: Optional[str] = None  # 'yallabalagan' сейчас, динамически в SaaS-фазе; None до миграции
    event_type: str = "internal"     # "internal" | "external"
    external_url: Optional[str] = None  # обязателен когда event_type="external"
    performer_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def generate_id() -> str:
        """Генерирует уникальный ID события"""
        return str(uuid.uuid4())

    def to_dynamodb_item(self) -> Dict:
        """Конвертирует в формат DynamoDB"""
        item = {
            "PK": f"EVENT#{self.event_id}",
            "SK": "METADATA",
            "event_id": self.event_id,
            "title": self.title,
            "description": self.description,
            "date": self.date,
            "location_id": self.location_id,
            "ticket_types": [tt.to_dict() for tt in self.ticket_types],
            "currency": self.currency,
            "images": self.images,
            "status": self.status,
            "recurrence": self.recurrence.to_dict() if self.recurrence else None,
            "refund_policy": self.refund_policy.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            # GSI для поиска по дате
            "GSI1PK": "EVENT",
            "GSI1SK": self.date
        }

        if self.slug:
            item["slug"] = self.slug

        if self.seat_allocation:
            item["seat_allocation"] = self.seat_allocation

        # owner_id и tenant_id добавляем только если заданы —
        # None не попадает в OwnerIndex GSI (ожидаемое поведение для legacy событий до миграции)
        if self.owner_id:
            item["owner_id"] = self.owner_id

        if self.tenant_id:
            item["tenant_id"] = self.tenant_id

        # event_type всегда присутствует; external_url и performer_ids — опционально
        item["event_type"] = self.event_type
        if self.external_url:
            item["external_url"] = self.external_url
        if self.performer_ids:
            item["performer_ids"] = self.performer_ids

        if self.tags:
            item["tags"] = self.tags

        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Event':
        """Создает объект из DynamoDB item"""
        ticket_types = [
            TicketType(**tt) for tt in item.get("ticket_types", [])
        ]

        recurrence = None
        if item.get("recurrence"):
            recurrence = Recurrence(**item["recurrence"])

        refund_policy_data = item.get("refund_policy", {})
        if refund_policy_data:
            refund_policy = RefundPolicy(**refund_policy_data)
        else:
            refund_policy = RefundPolicy()  # Use defaults

        return cls(
            event_id=item["event_id"],
            title=item["title"],
            description=item["description"],
            date=item["date"],
            location_id=item["location_id"],
            ticket_types=ticket_types,
            currency=item.get("currency", "ILS"),
            images=item.get("images", []),
            status=item.get("status", "active"),
            recurrence=recurrence,
            refund_policy=refund_policy,
            slug=item.get("slug"),
            seat_allocation=item.get("seat_allocation"),
            owner_id=item.get("owner_id"),
            tenant_id=item.get("tenant_id"),
            event_type=item.get("event_type", "internal"),
            external_url=item.get("external_url"),
            performer_ids=item.get("performer_ids", []),
            tags=item.get("tags", []),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at")
        )

    def is_sold_out(self) -> bool:
        """Проверяет, распроданы ли все билеты"""
        return all(tt.available == 0 for tt in self.ticket_types)

    def get_total_available(self) -> int:
        """Возвращает общее количество доступных билетов"""
        return sum(tt.available for tt in self.ticket_types)

    def get_ticket_type(self, type_id: str) -> Optional[TicketType]:
        """Находит тип билета по ID"""
        for tt in self.ticket_types:
            if tt.id == type_id:
                return tt
        return None

    def decrease_available(self, type_id: str, quantity: int) -> bool:
        """Уменьшает количество доступных билетов"""
        ticket_type = self.get_ticket_type(type_id)
        if not ticket_type:
            return False

        if ticket_type.available < quantity:
            return False

        ticket_type.available -= quantity
        self.updated_at = datetime.utcnow().isoformat()

        # Обновляем статус если распродано
        if self.is_sold_out():
            self.status = "sold_out"

        return True

    def increase_available(self, type_id: str, quantity: int) -> bool:
        """Увеличивает количество доступных билетов (при возврате)"""
        ticket_type = self.get_ticket_type(type_id)
        if not ticket_type:
            return False

        ticket_type.available += quantity
        self.updated_at = datetime.utcnow().isoformat()

        # Возвращаем статус active если было sold_out
        if self.status == "sold_out":
            self.status = "active"

        return True
