"""Show and Episode models for ticket service"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
import uuid
import re


@dataclass
class ShowLink:
    label: str
    url: str

    def to_dict(self) -> Dict:
        return {'label': self.label, 'url': self.url}

    @classmethod
    def from_dict(cls, data: Dict) -> 'ShowLink':
        return cls(label=data['label'], url=data['url'])


@dataclass
class Show:
    show_id: str
    name: str
    slug: str
    description: str
    short_description: str
    photo_url: Optional[str] = None
    links: List[ShowLink] = field(default_factory=list)
    tenant_id: Optional[str] = None
    allowed_tenants: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def generate_slug(name: str) -> str:
        slug = name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug or str(uuid.uuid4())[:8]

    def to_dynamodb_item(self) -> Dict:
        return {
            'PK': f'SHOW#{self.show_id}',
            'SK': 'METADATA',
            'show_id': self.show_id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'short_description': self.short_description,
            'photo_url': self.photo_url,
            'links': [l.to_dict() for l in self.links],
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'allowed_tenants': self.allowed_tenants,
            **({'tenant_id': self.tenant_id} if self.tenant_id else {}),
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Show':
        return cls(
            show_id=item['show_id'],
            name=item['name'],
            slug=item['slug'],
            description=item['description'],
            short_description=item['short_description'],
            photo_url=item.get('photo_url'),
            links=[ShowLink.from_dict(l) for l in item.get('links', [])],
            tenant_id=item.get('tenant_id'),
            allowed_tenants=item.get('allowed_tenants', []),
            created_at=item.get('created_at', ''),
            updated_at=item.get('updated_at', ''),
        )


@dataclass
class Episode:
    episode_id: str
    show_id: str
    number: int
    title: str
    slug: str
    description: str
    url: str
    thumbnail_url: Optional[str] = None
    performer_ids: List[str] = field(default_factory=list)
    published_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def generate_slug(show_slug: str, number: int, title: str) -> str:
        title_part = title.lower()
        title_part = re.sub(r'[^\w\s-]', '', title_part)
        title_part = re.sub(r'[\s_]+', '-', title_part)
        title_part = re.sub(r'-+', '-', title_part).strip('-')
        return f'{show_slug}-ep{number}-{title_part}'[:80]

    def to_dynamodb_item(self) -> Dict:
        return {
            'PK': f'EPISODE#{self.episode_id}',
            'SK': 'METADATA',
            'episode_id': self.episode_id,
            'show_id': self.show_id,
            'number': self.number,
            'title': self.title,
            'slug': self.slug,
            'description': self.description,
            'url': self.url,
            'thumbnail_url': self.thumbnail_url,
            'performer_ids': self.performer_ids,
            'published_at': self.published_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Episode':
        return cls(
            episode_id=item['episode_id'],
            show_id=item['show_id'],
            number=int(item['number']),
            title=item['title'],
            slug=item['slug'],
            description=item['description'],
            url=item['url'],
            thumbnail_url=item.get('thumbnail_url'),
            performer_ids=item.get('performer_ids', []),
            published_at=item.get('published_at', ''),
            created_at=item.get('created_at', ''),
            updated_at=item.get('updated_at', ''),
        )
