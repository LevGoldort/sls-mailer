"""Influencer model for the loyalty/referral program"""
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime
from decimal import Decimal
import uuid


@dataclass
class Influencer:
    influencer_id: str
    name: str
    email: str
    phone: str
    social_link: str
    audience_size: str
    coupon_code: str
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    total_sales: float = 0.0
    total_commission: float = 0.0
    orders_count: int = 0

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def to_dynamodb_item(self) -> Dict:
        return {
            "PK": f"INFLUENCER#{self.influencer_id}",
            "SK": "METADATA",
            "influencer_id": self.influencer_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "social_link": self.social_link,
            "audience_size": self.audience_size,
            "coupon_code": self.coupon_code,
            "status": self.status,
            "created_at": self.created_at,
            "total_sales": Decimal(str(round(self.total_sales, 2))),
            "total_commission": Decimal(str(round(self.total_commission, 2))),
            "orders_count": self.orders_count,
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Influencer':
        return cls(
            influencer_id=item["influencer_id"],
            name=item["name"],
            email=item["email"],
            phone=item.get("phone", ""),
            social_link=item.get("social_link", ""),
            audience_size=item.get("audience_size", ""),
            coupon_code=item["coupon_code"],
            status=item.get("status", "active"),
            created_at=item.get("created_at", ""),
            total_sales=float(item.get("total_sales", 0)),
            total_commission=float(item.get("total_commission", 0)),
            orders_count=int(item.get("orders_count", 0)),
        )

    def to_dict(self) -> Dict:
        return {
            "influencer_id": self.influencer_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "social_link": self.social_link,
            "audience_size": self.audience_size,
            "coupon_code": self.coupon_code,
            "status": self.status,
            "created_at": self.created_at,
            "total_sales": self.total_sales,
            "total_commission": self.total_commission,
            "orders_count": self.orders_count,
        }
