"""Tests for site-regenerator.py: fetch_data(), generate_sitemap(), generate_html_files()"""
import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add lambdas dir to path so we can import site-regenerator
sys.path.insert(0, str(Path(__file__).parent.parent / 'lambdas'))

import importlib
site_regen = importlib.import_module('site-regenerator')

fetch_data = site_regen.fetch_data
generate_sitemap = site_regen.generate_sitemap
generate_html_files = site_regen.generate_html_files
format_date = site_regen.format_date
format_time = site_regen.format_time

TEMPLATES_DIR = Path(__file__).parent.parent / 'frontend' / 'templates'

FUTURE_DATE = '2099-12-25T20:00:00'

SAMPLE_EVENT_INTERNAL = {
    'event_id': 'evt-001',
    'slug': 'new-years-show',
    'title': 'New Year Show',
    'date': FUTURE_DATE,
    'location_id': 'loc-001',
    'event_type': 'internal',
    'ticket_types': [{'id': 'tt-1', 'name': 'Standard', 'price': 50, 'available': 10, 'total': 20}],
    'performer_ids': ['perf-001'],
    'description': 'A great show',
    'images': [],
}

SAMPLE_EVENT_EXTERNAL = {
    'event_id': 'evt-002',
    'slug': 'external-event',
    'title': 'External Event',
    'date': FUTURE_DATE,
    'location_id': 'loc-001',
    'event_type': 'external',
    'external_url': 'https://example.com/tickets',
    'performer_ids': [],
    'description': 'Elsewhere',
    'images': [],
}

SAMPLE_LOCATION = {
    'location_id': 'loc-001',
    'slug': 'tel-aviv-venue',
    'name': 'Tel Aviv Venue',
    'address': '123 Dizengoff',
    'city': 'Tel Aviv',
}

SAMPLE_PERFORMER = {
    'performer_id': 'perf-001',
    'slug': 'john-doe',
    'name': 'John Doe',
    'status': 'active',
    'role': 'Comedian',
    'bio': 'Funny guy',
    'photo_url': None,
    'photos': [],
    'social': {},
    'youtube_embed': None,
}

SAMPLE_PRODUCT = {
    'product_id': 'prod-001',
    'performer_id': 'perf-001',
    'slug': 'john-tshirt',
    'name': 'John T-Shirt',
    'price_ils': 80,
    'status': 'active',
    'short_description': 'Cool shirt',
    'photo_url': None,
}


def _make_response(data):
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


# ── fetch_data ──────────────────────────────────────────────────────────────

class TestFetchData:
    def _mock_get(self, events=None, locations=None, performers=None, products=None):
        events = events or [SAMPLE_EVENT_INTERNAL]
        locations = locations or [SAMPLE_LOCATION]
        performers = performers or [SAMPLE_PERFORMER]
        products = products or [SAMPLE_PRODUCT]

        def side_effect(url, timeout=10):
            if url.endswith('/api/events'):
                return _make_response({'events': events})
            elif url.endswith('/api/locations'):
                return _make_response({'locations': locations})
            elif url.endswith('/api/performers'):
                return _make_response({'performers': performers})
            elif url.endswith('/api/products'):
                return _make_response({'products': products})
            raise ValueError(f"Unexpected URL: {url}")

        return side_effect

    def test_returns_four_values(self):
        with patch('requests.get', side_effect=self._mock_get()):
            result = fetch_data()
        assert len(result) == 4

    def test_events_have_date_formatted(self):
        with patch('requests.get', side_effect=self._mock_get()):
            events, _, _, _ = fetch_data()
        assert 'date_formatted' in events[0]

    def test_events_have_time_formatted(self):
        with patch('requests.get', side_effect=self._mock_get()):
            events, _, _, _ = fetch_data()
        assert 'time_formatted' in events[0]

    def test_internal_event_gets_min_price(self):
        with patch('requests.get', side_effect=self._mock_get()):
            events, _, _, _ = fetch_data()
        internal = next(e for e in events if e['event_id'] == 'evt-001')
        assert internal['min_price'] == 50

    def test_external_event_no_min_price(self):
        with patch('requests.get', side_effect=self._mock_get(
            events=[SAMPLE_EVENT_EXTERNAL]
        )):
            events, _, _, _ = fetch_data()
        assert 'min_price' not in events[0]

    def test_event_gets_performer_objects_attached(self):
        with patch('requests.get', side_effect=self._mock_get()):
            events, _, _, _ = fetch_data()
        internal = next(e for e in events if e['event_id'] == 'evt-001')
        assert len(internal['performers']) == 1
        assert internal['performers'][0]['name'] == 'John Doe'

    def test_event_performer_ids_not_in_map_are_skipped(self):
        event = {**SAMPLE_EVENT_INTERNAL, 'performer_ids': ['perf-999']}
        with patch('requests.get', side_effect=self._mock_get(events=[event])):
            events, _, _, _ = fetch_data()
        assert events[0]['performers'] == []

    def test_performer_products_map_built(self):
        with patch('requests.get', side_effect=self._mock_get()):
            _, _, _, performer_products_map = fetch_data()
        assert 'perf-001' in performer_products_map
        assert performer_products_map['perf-001'][0]['product_id'] == 'prod-001'

    def test_performers_fetch_failure_is_nonfatal(self):
        def side_effect(url, timeout=10):
            if url.endswith('/api/performers'):
                raise Exception("network error")
            if url.endswith('/api/events'):
                return _make_response({'events': [SAMPLE_EVENT_INTERNAL]})
            if url.endswith('/api/locations'):
                return _make_response({'locations': [SAMPLE_LOCATION]})
            if url.endswith('/api/products'):
                return _make_response({'products': []})

        with patch('requests.get', side_effect=side_effect):
            events, locations, performers, performer_products_map = fetch_data()
        assert performers == []
        assert performer_products_map == {}

    def test_products_fetch_failure_is_nonfatal(self):
        def side_effect(url, timeout=10):
            if url.endswith('/api/products'):
                raise Exception("network error")
            if url.endswith('/api/events'):
                return _make_response({'events': [SAMPLE_EVENT_INTERNAL]})
            if url.endswith('/api/locations'):
                return _make_response({'locations': [SAMPLE_LOCATION]})
            if url.endswith('/api/performers'):
                return _make_response({'performers': [SAMPLE_PERFORMER]})

        with patch('requests.get', side_effect=side_effect):
            _, _, _, performer_products_map = fetch_data()
        assert performer_products_map == {}


# ── generate_sitemap ─────────────────────────────────────────────────────────

class TestGenerateSitemap:
    def test_homepage_included(self):
        xml = generate_sitemap([], [])
        assert 'https://yallabalagan.org/' in xml

    def test_event_included(self):
        xml = generate_sitemap([SAMPLE_EVENT_INTERNAL], [])
        assert 'https://yallabalagan.org/events/evt-001.html' in xml

    def test_location_slug_used(self):
        xml = generate_sitemap([], [SAMPLE_LOCATION])
        assert 'https://yallabalagan.org/locations/tel-aviv-venue.html' in xml

    def test_performer_with_slug_included(self):
        xml = generate_sitemap([], [], performers=[SAMPLE_PERFORMER])
        assert 'https://yallabalagan.org/performer/john-doe/' in xml

    def test_performer_without_slug_excluded(self):
        performer_no_slug = {**SAMPLE_PERFORMER, 'slug': None}
        xml = generate_sitemap([], [], performers=[performer_no_slug])
        assert '/performer/' not in xml

    def test_no_performers_arg_still_works(self):
        xml = generate_sitemap([SAMPLE_EVENT_INTERNAL], [SAMPLE_LOCATION])
        assert 'yallabalagan.org' in xml

    def test_accessibility_page_included(self):
        xml = generate_sitemap([], [])
        assert 'accessibility.html' in xml


# ── generate_html_files ───────────────────────────────────────────────────────

class TestGenerateHtmlFiles:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, events=None, locations=None, performers=None, performer_products_map=None):
        events = events or []
        locations = locations or []
        generate_html_files(
            events, locations, self.tmp, TEMPLATES_DIR,
            performers=performers,
            performer_products_map=performer_products_map or {},
        )

    def test_index_html_generated(self):
        self._run()
        assert (self.tmp / 'index.html').exists()

    def test_event_page_generated_by_id(self):
        event = {**SAMPLE_EVENT_INTERNAL, 'date_formatted': '25 декабря 2099', 'time_formatted': '20:00', 'performers': []}
        self._run(events=[event], locations=[SAMPLE_LOCATION])
        assert (self.tmp / 'events' / 'evt-001.html').exists()

    def test_event_slug_page_generated(self):
        event = {**SAMPLE_EVENT_INTERNAL, 'date_formatted': '25 декабря 2099', 'time_formatted': '20:00', 'performers': []}
        self._run(events=[event], locations=[SAMPLE_LOCATION])
        assert (self.tmp / 'events' / 'new-years-show.html').exists()

    def test_location_page_generated(self):
        self._run(locations=[SAMPLE_LOCATION])
        assert (self.tmp / 'locations' / 'tel-aviv-venue.html').exists()

    def test_performer_page_generated(self):
        self._run(performers=[SAMPLE_PERFORMER])
        assert (self.tmp / 'performer' / 'john-doe' / 'index.html').exists()

    def test_performer_without_slug_skipped(self):
        performer_no_slug = {**SAMPLE_PERFORMER, 'slug': None}
        self._run(performers=[performer_no_slug])
        performer_dir = self.tmp / 'performer'
        # Directory may be created but no index.html files should exist
        assert not list(performer_dir.rglob('index.html'))

    def test_performer_page_contains_name(self):
        self._run(performers=[SAMPLE_PERFORMER])
        content = (self.tmp / 'performer' / 'john-doe' / 'index.html').read_text()
        assert 'John Doe' in content

    def test_performer_page_contains_product(self):
        self._run(
            performers=[SAMPLE_PERFORMER],
            performer_products_map={'perf-001': [SAMPLE_PRODUCT]},
        )
        content = (self.tmp / 'performer' / 'john-doe' / 'index.html').read_text()
        assert 'John T-Shirt' in content

    def test_sitemap_generated(self):
        self._run()
        assert (self.tmp / 'sitemap.xml').exists()

    def test_sitemap_contains_performer_url(self):
        self._run(performers=[SAMPLE_PERFORMER])
        sitemap = (self.tmp / 'sitemap.xml').read_text()
        assert 'john-doe' in sitemap

    def test_external_event_shows_link_button(self):
        event = {**SAMPLE_EVENT_EXTERNAL, 'date_formatted': '25 декабря 2099', 'time_formatted': '20:00', 'performers': []}
        self._run(events=[event], locations=[SAMPLE_LOCATION])
        content = (self.tmp / 'events' / 'evt-002.html').read_text()
        assert 'https://example.com/tickets' in content

    def test_index_shows_external_badge(self):
        event = {**SAMPLE_EVENT_EXTERNAL, 'date_formatted': '25 декабря 2099', 'time_formatted': '20:00', 'performers': []}
        self._run(events=[event], locations=[SAMPLE_LOCATION])
        content = (self.tmp / 'index.html').read_text()
        assert 'Внешнее событие' in content

    def test_checkout_html_generated(self):
        self._run()
        assert (self.tmp / 'checkout.html').exists()

    def test_processing_html_generated(self):
        self._run()
        assert (self.tmp / 'processing.html').exists()

    def test_accessibility_html_generated(self):
        self._run()
        assert (self.tmp / 'accessibility.html').exists()
