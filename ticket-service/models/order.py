"""Order model for ticket service"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from datetime import datetime, timezone
import uuid
import random
import string


@dataclass
class Customer:
    """Информация о покупателе"""
    name: str
    email: str
    phone: str

    def to_dict(self):
        return asdict(self)


@dataclass
class OrderTicket:
    """Билет в заказе"""
    type_id: str
    type_name: str
    quantity: int
    price_per_ticket: float
    purchased_seats: Optional[List[str]] = None  # NEW: ["0-5", "0-6"] for seated events

    def get_total(self) -> float:
        # Convert to float to handle Decimal types from DynamoDB
        return float(self.quantity) * float(self.price_per_ticket)

    def to_dict(self):
        from decimal import Decimal
        result = {
            'type_id': self.type_id,
            'type_name': self.type_name,
            'quantity': self.quantity,
            'price_per_ticket': Decimal(str(self.price_per_ticket))
        }
        if self.purchased_seats:  # Only include if present
            result['purchased_seats'] = self.purchased_seats
        return result


@dataclass
class QRCode:
    """QR код для билета"""
    code: str
    ticket_type: str
    s3_url: Optional[str] = None
    seat_id: Optional[str] = None  # NEW: "13-15" (row-seat) for seated events
    scanned: bool = False
    scanned_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class Refund:
    """Информация о возврате"""
    requested_at: str
    processed_at: Optional[str] = None
    amount: float = 0
    reason: str = "customer_request"  # "customer_request" | "event_cancelled"

    def to_dict(self):
        return asdict(self)


@dataclass
class Payment:
    """Информация об оплате"""
    status: str  # "pending" | "completed" | "failed" | "refunded"
    allpay_transaction_id: Optional[str] = None
    paid_at: Optional[str] = None
    refund: Optional[Refund] = None

    def to_dict(self):
        result = asdict(self)
        if self.refund:
            result["refund"] = self.refund.to_dict()
        return result


@dataclass
class Notifications:
    """Статус уведомлений"""
    email_sent: bool = False
    sms_sent: bool = False
    reminder_sent: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass
class Order:
    """Модель заказа/билета"""
    order_id: str
    event_id: str
    customer: Customer
    tickets: List[OrderTicket]
    total_amount: float
    currency: str = "ILS"
    payment: Payment = field(default_factory=lambda: Payment(status="pending"))
    qr_codes: List[QRCode] = field(default_factory=list)
    notifications: Notifications = field(default_factory=Notifications)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    coupon_code: Optional[str] = None
    discount_amount: float = 0

    @staticmethod
    def generate_id() -> str:
        """Генерирует уникальный ID заказа"""
        return str(uuid.uuid4())

    @staticmethod
    def generate_ticket_code(event_id: str, index: int = 1) -> str:
        """
        Генерирует читаемый код билета
        Формат: YBEV-2025-XXXX-N
        """
        year = datetime.utcnow().year
        # Последние 4 символа event_id
        event_short = event_id[-4:].upper()
        # Случайные 4 символа
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"YBEV-{year}-{event_short}-{random_part}-{index}"

    def calculate_total(self) -> float:
        """Вычисляет общую сумму заказа"""
        return sum(ticket.get_total() for ticket in self.tickets)

    def generate_qr_codes(self, generate_images: bool = True):
        """
        Генерирует QR коды для всех билетов в заказе

        Args:
            generate_images: Если True, генерирует QR изображения и загружает в S3
        """
        self.qr_codes = []
        index = 1

        for ticket in self.tickets:
            # Get purchased seats for this ticket type (if seated event)
            purchased_seats = ticket.purchased_seats if ticket.purchased_seats else []
            seat_index = 0

            for _ in range(int(ticket.quantity)):
                code = self.generate_ticket_code(self.event_id, index)

                # Assign seat if available
                seat_id = purchased_seats[seat_index] if seat_index < len(purchased_seats) else None

                # Generate QR image if requested
                s3_url = None
                if generate_images:
                    try:
                        from utils.qr_generator import generate_qr_image
                        s3_url = generate_qr_image(code, self.order_id)
                    except Exception as e:
                        print(f"Warning: Failed to generate QR image for {code}: {str(e)}")
                        # Continue without image - code is still valid

                qr = QRCode(
                    code=code,
                    ticket_type=ticket.type_id,
                    s3_url=s3_url,
                    seat_id=seat_id  # NEW: Assign seat to QR code
                )
                self.qr_codes.append(qr)
                index += 1
                seat_index += 1

    def to_dynamodb_item(self) -> Dict:
        """Конвертирует в формат DynamoDB"""
        from decimal import Decimal

        item = {
            "PK": f"ORDER#{self.order_id}",
            "SK": "METADATA",
            "order_id": self.order_id,
            "event_id": self.event_id,
            "customer": self.customer.to_dict(),
            "tickets": [t.to_dict() for t in self.tickets],
            "total_amount": Decimal(str(self.total_amount)),
            "currency": self.currency,
            "payment": self.payment.to_dict(),
            "qr_codes": [qr.to_dict() for qr in self.qr_codes],
            "notifications": self.notifications.to_dict(),
            "created_at": self.created_at,
            # GSI для поиска
            "customer_email": self.customer.email
        }

        # Add coupon fields if present
        if self.coupon_code:
            item["coupon_code"] = self.coupon_code
            item["discount_amount"] = Decimal(str(self.discount_amount))

        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Order':
        """Создает объект из DynamoDB item"""
        customer = Customer(**item["customer"])

        tickets = [
            OrderTicket(
                type_id=t['type_id'],
                type_name=t['type_name'],
                quantity=t['quantity'],
                price_per_ticket=t['price_per_ticket'],
                purchased_seats=t.get('purchased_seats')  # Backward compatible
            )
            for t in item["tickets"]
        ]

        payment_data = item["payment"]
        refund = None
        if payment_data.get("refund"):
            refund = Refund(**payment_data["refund"])

        payment = Payment(
            status=payment_data["status"],
            allpay_transaction_id=payment_data.get("allpay_transaction_id"),
            paid_at=payment_data.get("paid_at"),
            refund=refund
        )

        qr_codes = [QRCode(**qr) for qr in item.get("qr_codes", [])]

        notifications = Notifications(**item.get("notifications", {}))

        return cls(
            order_id=item["order_id"],
            event_id=item["event_id"],
            customer=customer,
            tickets=tickets,
            total_amount=item["total_amount"],
            currency=item.get("currency", "ILS"),
            payment=payment,
            qr_codes=qr_codes,
            notifications=notifications,
            created_at=item.get("created_at"),
            coupon_code=item.get("coupon_code"),
            discount_amount=item.get("discount_amount", 0)
        )

    def can_refund(self, event_date: str, hours_before: int = 48) -> tuple[bool, str]:
        """
        Проверяет возможность возврата билета

        Returns:
            (can_refund, reason)
        """
        # Проверка статуса оплаты
        if self.payment.status != "completed":
            return False, "Оплата не завершена"

        if self.payment.status == "refunded":
            return False, "Заказ уже возвращен"

        # Проверка времени до события
        event_dt = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        hours_until = (event_dt - now).total_seconds() / 3600

        if hours_until < hours_before:
            return False, f"Возврат возможен только за {hours_before}+ часов до события"

        return True, "OK"
