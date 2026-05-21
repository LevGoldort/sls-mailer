"""Performer model for ticket service"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
import uuid


@dataclass
class SocialLinks:
    instagram: Optional[str] = None
    telegram: Optional[str] = None
    youtube: Optional[str] = None
    facebook: Optional[str] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in {
            'instagram': self.instagram,
            'telegram': self.telegram,
            'youtube': self.youtube,
            'facebook': self.facebook,
        }.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict) -> 'SocialLinks':
        return cls(
            instagram=data.get('instagram'),
            telegram=data.get('telegram'),
            youtube=data.get('youtube'),
            facebook=data.get('facebook'),
        )


@dataclass
class Performer:
    performer_id: str
    tenant_id: str
    name: str
    slug: str
    bio: str
    role: str
    photo_url: str
    photos: List[str] = field(default_factory=list)
    youtube_embed: Optional[str] = None
    social: SocialLinks = field(default_factory=SocialLinks)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    status: str = "active"  # "active" | "inactive"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    def to_dynamodb_item(self) -> Dict:
        item = {
            'PK': f'PERFORMER#{self.performer_id}',
            'SK': 'METADATA',
            'performer_id': self.performer_id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'slug': self.slug,
            'bio': self.bio,
            'role': self.role,
            'photo_url': self.photo_url,
            'photos': self.photos,
            'social': self.social.to_dict(),
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            # GSI keys
            'GSI1PK': f'TENANT#{self.tenant_id}',
            'GSI1SK': f'{self.status}#{self.performer_id}',
        }
        if self.youtube_embed:
            item['youtube_embed'] = self.youtube_embed
        if self.contact_email:
            item['contact_email'] = self.contact_email
        if self.contact_phone:
            item['contact_phone'] = self.contact_phone
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> 'Performer':
        social_data = item.get('social', {})
        return cls(
            performer_id=item['performer_id'],
            tenant_id=item.get('tenant_id', 'yallabalagan'),
            name=item['name'],
            slug=item['slug'],
            bio=item.get('bio', ''),
            role=item.get('role', ''),
            photo_url=item.get('photo_url', ''),
            photos=item.get('photos', []),
            youtube_embed=item.get('youtube_embed'),
            social=SocialLinks.from_dict(social_data) if social_data else SocialLinks(),
            contact_email=item.get('contact_email'),
            contact_phone=item.get('contact_phone'),
            status=item.get('status', 'active'),
            created_at=item.get('created_at'),
            updated_at=item.get('updated_at'),
        )
