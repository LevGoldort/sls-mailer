"""Product (merchandise) model for ticket service"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
from decimal import Decimal
import uuid


@dataclass
class Product:
    product_id: str
    tenant_id: str
    performer_id: str
    name: str
    slug: str
    short_description: str
    price_ils: float
    photo_url: str
    full_description: str = ""
    what_you_get: str = ""
    gallery_urls: List[str] = field(default_factory=list)
    total_slots: Optional[int] = None  # None = unlimited
    sold_slots: int = 0
    status: str = "active"  # "active" | "inactive" | "sold_out"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    def to_dynamodb_item(self) -> Dict:
        item = {
            'PK': f'PRODUCT#{self.product_id}',
            'SK': 'METADATA',
            'product_id': self.product_id,
            'tenant_id': self.tenant_id,
            'performer_id': self.performer_id,
            'name': self.name,
            'slug': self.slug,
            'short_description': self.short_description,
            'full_description': self.full_description,
            'what_you_get': self.what_you_get,
            'price_ils': Decimal(str(self.price_ils)),
            'photo_url': self.photo_url,
            'gallery_urls': self.gallery_urls,
            'sold_slots': self.sold_slots,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            # GSI keys
            'GSI1PK': f'PERFORMER#{self.performer_id}',
            'GSI1SK': self.updated_at,
            'GSI2PK': self.status,
            'GSI2SK': self.updated_at,
        }
        if self.total_slots is not None:
            item['total_slots'] = self.total_slots
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Product':
        return cls(
            product_id=item['product_id'],
            tenant_id=item.get('tenant_id', 'yallabalagan'),
            performer_id=item['performer_id'],
            name=item['name'],
            slug=item['slug'],
            short_description=item.get('short_description', ''),
            full_description=item.get('full_description', ''),
            what_you_get=item.get('what_you_get', ''),
            price_ils=float(item.get('price_ils', 0)),
            photo_url=item.get('photo_url', ''),
            gallery_urls=item.get('gallery_urls', []),
            total_slots=item.get('total_slots'),
            sold_slots=int(item.get('sold_slots', 0)),
            status=item.get('status', 'active'),
            created_at=item.get('created_at'),
            updated_at=item.get('updated_at'),
        )
