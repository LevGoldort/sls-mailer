"""Merchandise order model for ticket service"""
from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime
from decimal import Decimal
import uuid


@dataclass
class BuyerInfo:
    name: str
    email: str
    phone: Optional[str] = None
    telegram: Optional[str] = None

    def to_dict(self) -> Dict:
        d = {'name': self.name, 'email': self.email}
        if self.phone:
            d['phone'] = self.phone
        if self.telegram:
            d['telegram'] = self.telegram
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> 'BuyerInfo':
        return cls(
            name=data['name'],
            email=data['email'],
            phone=data.get('phone'),
            telegram=data.get('telegram'),
        )


@dataclass
class MerchandiseOrder:
    order_id: str
    product_id: str
    product_slug: str
    performer_id: str
    buyer: BuyerInfo
    amount_ils: float
    payment_method: str = "allpay"  # "allpay" | "mock"
    payment_id: Optional[str] = None
    status: str = "pending"  # "pending" | "completed" | "failed"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def generate_id() -> str:
        return f"merch-{uuid.uuid4()}"

    def to_dynamodb_item(self) -> Dict:
        item = {
            'PK': f'MERCH_ORDER#{self.order_id}',
            'SK': 'METADATA',
            'order_id': self.order_id,
            'product_id': self.product_id,
            'product_slug': self.product_slug,
            'performer_id': self.performer_id,
            'buyer': self.buyer.to_dict(),
            'buyer_email': self.buyer.email,  # denormalized for EmailIndex GSI
            'amount_ils': Decimal(str(self.amount_ils)),
            'payment_method': self.payment_method,
            'status': self.status,
            'created_at': self.created_at,
            # GSI keys
            'GSI1PK': self.buyer.email,
            'GSI1SK': self.created_at,
            'GSI2PK': f'PRODUCT#{self.product_id}',
            'GSI2SK': self.created_at,
        }
        if self.payment_id:
            item['payment_id'] = self.payment_id
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'MerchandiseOrder':
        return cls(
            order_id=item['order_id'],
            product_id=item['product_id'],
            product_slug=item.get('product_slug', ''),
            performer_id=item['performer_id'],
            buyer=BuyerInfo.from_dict(item['buyer']),
            amount_ils=float(item.get('amount_ils', 0)),
            payment_method=item.get('payment_method', 'allpay'),
            payment_id=item.get('payment_id'),
            status=item.get('status', 'pending'),
            created_at=item.get('created_at'),
        )
