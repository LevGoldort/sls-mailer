"""User model for ticket service"""
from dataclasses import dataclass, asdict
from typing import Optional, Dict
from datetime import datetime
import uuid


TENANT_ID = "yallabalagan"  # Hardcoded now, dynamic in SaaS phase


@dataclass
class User:
    """Модель пользователя системы"""
    user_id: str
    tenant_id: str   # 'yallabalagan' сейчас, динамически в SaaS-фазе
    email: str
    password_hash: str
    name: str
    role: str        # 'platform_admin' | 'admin' | 'organizer' | 'content_manager'
    status: str      # 'active' | 'inactive'
    created_at: str
    updated_at: str

    @staticmethod
    def generate_id() -> str:
        """Генерирует уникальный ID пользователя"""
        return str(uuid.uuid4())

    def to_dynamodb_item(self) -> Dict:
        """Конвертирует в формат DynamoDB"""
        return {
            "PK": f"TENANT#{self.tenant_id}#USER#{self.user_id}",
            "SK": "METADATA",
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "password_hash": self.password_hash,
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> "User":
        """Создаёт объект из DynamoDB item"""
        return cls(
            user_id=item["user_id"],
            tenant_id=item["tenant_id"],
            email=item["email"],
            password_hash=item["password_hash"],
            name=item["name"],
            role=item["role"],
            status=item.get("status", "active"),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )

    def to_dict(self) -> Dict:
        """Конвертирует в словарь (включая password_hash — только для внутреннего использования)"""
        return asdict(self)

    def to_api_dict(self) -> Dict:
        """Конвертирует в словарь для API-ответов (без password_hash)"""
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def is_active(self) -> bool:
        """Проверяет, активен ли пользователь"""
        return self.status == "active"

    def is_admin(self) -> bool:
        """Проверяет, является ли пользователь администратором"""
        return self.role == "admin"

    @staticmethod
    def create(
        email: str,
        password_hash: str,
        name: str,
        role: str,
        tenant_id: str = TENANT_ID,
        user_id: Optional[str] = None,
    ) -> "User":
        """Фабричный метод для создания нового пользователя"""
        now = datetime.utcnow().isoformat()
        return User(
            user_id=user_id or User.generate_id(),
            tenant_id=tenant_id,
            email=email,
            password_hash=password_hash,
            name=name,
            role=role,
            status="active",
            created_at=now,
            updated_at=now,
        )
