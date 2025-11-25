"""Location model for ticket service"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from datetime import datetime
from decimal import Decimal
import uuid


@dataclass
class Coordinates:
    """Географические координаты"""
    lat: float
    lng: float

    def to_dict(self):
        return {
            'lat': Decimal(str(self.lat)),
            'lng': Decimal(str(self.lng))
        }


@dataclass
class Address:
    """Адрес локации"""
    street: str
    city: str
    coordinates: Coordinates

    def to_dict(self):
        result = asdict(self)
        result["coordinates"] = self.coordinates.to_dict()
        return result


@dataclass
class Parking:
    """Информация о парковке (упрощенная)"""
    description: str  # "Подземная парковка в 100 метрах от заведения"
    coordinates: Coordinates
    google_maps_url: Optional[str] = None

    def to_dict(self):
        return {
            "description": self.description,
            "coordinates": self.coordinates.to_dict(),
            "google_maps_url": self.google_maps_url
        }


@dataclass
class Media:
    """Медиа контент локации"""
    photos: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class Contact:
    """Контактная информация"""
    phone: Optional[str] = None
    email: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class Location:
    """Модель локации/заведения"""
    location_id: str
    name: str
    slug: str
    address: Address
    description: str  # Полное описание для страницы локации
    short_description: str  # Короткое описание для страницы события
    capacity: int
    featured_image: Optional[str] = None  # Главное фото (URL на S3)
    media: Media = field(default_factory=Media)
    parkings: List[Parking] = field(default_factory=list)
    amenities: List[str] = field(default_factory=list)
    contact: Contact = field(default_factory=Contact)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def generate_id() -> str:
        """Генерирует уникальный ID локации"""
        return str(uuid.uuid4())

    @staticmethod
    def generate_slug(name: str) -> str:
        """Генерирует slug из названия"""
        # Простая версия - можно улучшить
        import re
        slug = name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_-]+', '-', slug)
        slug = slug.strip('-')
        return slug

    def to_dynamodb_item(self) -> Dict:
        """Конвертирует в формат DynamoDB"""
        return {
            "PK": f"LOCATION#{self.location_id}",
            "SK": "METADATA",
            "location_id": self.location_id,
            "name": self.name,
            "slug": self.slug,
            "address": self.address.to_dict(),
            "description": self.description,
            "short_description": self.short_description,
            "capacity": Decimal(str(self.capacity)) if isinstance(self.capacity, (int, float)) else self.capacity,
            "featured_image": self.featured_image,
            "media": self.media.to_dict(),
            "parkings": [p.to_dict() for p in self.parkings],
            "amenities": self.amenities,
            "contact": self.contact.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Location':
        """Создает объект из DynamoDB item"""
        address_data = item["address"]
        address = Address(
            street=address_data["street"],
            city=address_data["city"],
            coordinates=Coordinates(**address_data["coordinates"])
        )

        media = Media(**item.get("media", {}))

        parkings = []
        for p in item.get("parkings", []):
            parkings.append(Parking(
                description=p["description"],
                coordinates=Coordinates(**p["coordinates"]),
                google_maps_url=p.get("google_maps_url")
            ))

        contact = Contact(**item.get("contact", {}))

        return cls(
            location_id=item["location_id"],
            name=item["name"],
            slug=item["slug"],
            address=address,
            description=item["description"],
            short_description=item.get("short_description", ""),
            capacity=item["capacity"],
            featured_image=item.get("featured_image"),
            media=media,
            parkings=parkings,
            amenities=item.get("amenities", []),
            contact=contact,
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at")
        )
