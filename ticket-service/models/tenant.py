"""Tenant model for multi-tenant platform"""
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime
import uuid


@dataclass
class Tenant:
    tenant_id: str
    name: str
    slug: str
    status: str = "active"  # "active" | "inactive"
    created_at: str = ""
    updated_at: str = ""

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def create(name: str, slug: str, tenant_id: Optional[str] = None) -> "Tenant":
        now = datetime.utcnow().isoformat()
        return Tenant(
            tenant_id=tenant_id or Tenant.generate_id(),
            name=name,
            slug=slug,
            status="active",
            created_at=now,
            updated_at=now,
        )

    def to_dynamodb_item(self) -> Dict:
        return {
            "PK": f"TENANT#{self.tenant_id}",
            "SK": "METADATA",
            "tenant_id": self.tenant_id,
            "name": self.name,
            "slug": self.slug,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> "Tenant":
        return cls(
            tenant_id=item["tenant_id"],
            name=item["name"],
            slug=item["slug"],
            status=item.get("status", "active"),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )

    def to_api_dict(self) -> Dict:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "slug": self.slug,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
