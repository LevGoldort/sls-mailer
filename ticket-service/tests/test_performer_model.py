"""Unit tests for Performer and SocialLinks models (Task 22)."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.performer import Performer, SocialLinks


class TestSocialLinks:
    def test_to_dict_excludes_none_values(self):
        s = SocialLinks(instagram='@test', telegram=None, youtube=None, facebook=None)
        d = s.to_dict()
        assert d == {'instagram': '@test'}
        assert 'telegram' not in d

    def test_to_dict_all_none_returns_empty(self):
        assert SocialLinks().to_dict() == {}

    def test_to_dict_all_filled(self):
        s = SocialLinks(instagram='@ig', telegram='@tg', youtube='yt.com/c/x', facebook='fb.com/x')
        d = s.to_dict()
        assert d == {'instagram': '@ig', 'telegram': '@tg', 'youtube': 'yt.com/c/x', 'facebook': 'fb.com/x'}

    def test_from_dict_roundtrip(self):
        original = SocialLinks(instagram='@ig', telegram='@tg')
        restored = SocialLinks.from_dict(original.to_dict())
        assert restored.instagram == '@ig'
        assert restored.telegram == '@tg'
        assert restored.youtube is None

    def test_from_dict_empty(self):
        s = SocialLinks.from_dict({})
        assert s.instagram is None
        assert s.telegram is None


class TestPerformer:
    def _make(self, **kwargs):
        defaults = dict(
            performer_id='p-123',
            tenant_id='yallabalagan',
            name='DJ Test',
            slug='dj-test',
            bio='Bio text',
            role='DJ',
            photo_url='https://cdn.example.com/photo.jpg',
        )
        defaults.update(kwargs)
        return Performer(**defaults)

    def test_generate_id_returns_string(self):
        pid = Performer.generate_id()
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_to_dynamodb_item_keys(self):
        p = self._make()
        item = p.to_dynamodb_item()
        assert item['PK'] == 'PERFORMER#p-123'
        assert item['SK'] == 'METADATA'

    def test_to_dynamodb_item_gsi_keys(self):
        p = self._make(status='active')
        item = p.to_dynamodb_item()
        assert item['GSI1PK'] == 'TENANT#yallabalagan'
        assert item['GSI1SK'] == 'active#p-123'

    def test_to_dynamodb_item_gsi_sk_uses_status(self):
        p = self._make(performer_id='p-456', status='inactive')
        item = p.to_dynamodb_item()
        assert item['GSI1SK'] == 'inactive#p-456'

    def test_optional_fields_absent_when_none(self):
        p = self._make(youtube_embed=None, contact_email=None, contact_phone=None)
        item = p.to_dynamodb_item()
        assert 'youtube_embed' not in item
        assert 'contact_email' not in item
        assert 'contact_phone' not in item

    def test_optional_fields_present_when_set(self):
        p = self._make(youtube_embed='yt-id', contact_email='a@b.com', contact_phone='+972501234')
        item = p.to_dynamodb_item()
        assert item['youtube_embed'] == 'yt-id'
        assert item['contact_email'] == 'a@b.com'
        assert item['contact_phone'] == '+972501234'

    def test_social_links_serialized(self):
        p = self._make(social=SocialLinks(instagram='@ig'))
        item = p.to_dynamodb_item()
        assert item['social'] == {'instagram': '@ig'}

    def test_from_dynamodb_item_roundtrip(self):
        p = self._make(
            social=SocialLinks(instagram='@ig', telegram='@tg'),
            youtube_embed='yt-embed',
            contact_email='dj@example.com',
        )
        restored = Performer.from_dynamodb_item(p.to_dynamodb_item())
        assert restored.performer_id == p.performer_id
        assert restored.name == p.name
        assert restored.slug == p.slug
        assert restored.bio == p.bio
        assert restored.role == p.role
        assert restored.tagline == p.tagline
        assert restored.social.instagram == '@ig'
        assert restored.social.telegram == '@tg'
        assert restored.youtube_embed == 'yt-embed'
        assert restored.contact_email == 'dj@example.com'

    def test_tagline_optional(self):
        p = self._make()
        assert p.tagline is None
        item = p.to_dynamodb_item()
        assert item['tagline'] is None
        restored = Performer.from_dynamodb_item(item)
        assert restored.tagline is None

    def test_tagline_roundtrip(self):
        p = self._make(tagline='Тель-Авивский комик, автор шоу Изотоп Комедия')
        restored = Performer.from_dynamodb_item(p.to_dynamodb_item())
        assert restored.tagline == p.tagline

    def test_from_dynamodb_item_defaults_tenant_id(self):
        item = {
            'performer_id': 'p-1',
            'name': 'Test',
            'slug': 'test',
        }
        p = Performer.from_dynamodb_item(item)
        assert p.tenant_id == 'yallabalagan'
        assert p.status == 'active'
        assert p.social.instagram is None

    def test_photos_default_empty_list(self):
        p = self._make()
        assert p.photos == []
        assert p.to_dynamodb_item()['photos'] == []
