"""Tests for site-regenerator.py: fetch_data(), generate_sitemap(), generate_html_files(),
group_events_by_month(), collect_tags()"""
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
group_events_by_month = site_regen.group_events_by_month
collect_tags = site_regen.collect_tags

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
    'tags': ['Comedy'],
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
    'tags': [],
}

SAMPLE_LOCATION = {
    'location_id': 'loc-001',
    'slug': 'tel-aviv-venue',
    'name': 'Tel Aviv Venue',
    'address': {
        'street': '123 Dizengoff',
        'city': 'Tel Aviv',
        'coordinates': {},
    },
    'description': '',
    'media': {'photos': []},
    'parkings': [],
}

SAMPLE_PERFORMER = {
    'performer_id': 'perf-001',
    'slug': 'john-doe',
    'name': 'John Doe',
    'status': 'active',
    'role': 'Comedian',
    'bio': 'Funny guy',
    'tagline': None,
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

    def test_returns_dict(self):
        with patch('requests.get', side_effect=self._mock_get()):
            result = fetch_data()
        assert isinstance(result, dict)

    def test_returns_expected_keys(self):
        with patch('requests.get', side_effect=self._mock_get()):
            result = fetch_data()
        for key in ('events', 'locations', 'performers', 'products',
                    'performer_products_map', 'performer_upcoming', 'performer_archive',
                    'location_events_map'):
            assert key in result, f"Missing key: {key}"

    def test_events_have_date_formatted(self):
        with patch('requests.get', side_effect=self._mock_get()):
            result = fetch_data()
        assert 'date_formatted' in result['events'][0]

    def test_events_have_time_formatted(self):
        with patch('requests.get', side_effect=self._mock_get()):
            result = fetch_data()
        assert 'time_formatted' in result['events'][0]

    def test_internal_event_gets_min_price(self):
        with patch('requests.get', side_effect=self._mock_get()):
            result = fetch_data()
        internal = next(e for e in result['events'] if e['event_id'] == 'evt-001')
        assert internal['min_price'] == 50

    def test_external_event_no_min_price(self):
        with patch('requests.get', side_effect=self._mock_get(
            events=[SAMPLE_EVENT_EXTERNAL]
        )):
            result = fetch_data()
        assert 'min_price' not in result['events'][0]

    def test_event_gets_performer_objects_attached(self):
        with patch('requests.get', side_effect=self._mock_get()):
            result = fetch_data()
        internal = next(e for e in result['events'] if e['event_id'] == 'evt-001')
        assert len(internal['performers']) == 1
        assert internal['performers'][0]['name'] == 'John Doe'

    def test_event_performer_ids_not_in_map_are_skipped(self):
        event = {**SAMPLE_EVENT_INTERNAL, 'performer_ids': ['perf-999']}
        with patch('requests.get', side_effect=self._mock_get(events=[event])):
            result = fetch_data()
        assert result['events'][0]['performers'] == []

    def test_performer_products_map_built(self):
        with patch('requests.get', side_effect=self._mock_get()):
            result = fetch_data()
        assert 'perf-001' in result['performer_products_map']
        assert result['performer_products_map']['perf-001'][0]['product_id'] == 'prod-001'

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
            result = fetch_data()
        assert result['performers'] == []
        assert result['performer_products_map'] == {}

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
            result = fetch_data()
        assert result['performer_products_map'] == {}


# ── group_events_by_month ────────────────────────────────────────────────────

class TestGroupEventsByMonth:
    def test_empty_returns_empty(self):
        assert group_events_by_month([]) == []

    def test_single_event_one_group(self):
        events = [{'date': '2099-06-15T19:00:00', 'event_id': 'e1'}]
        groups = group_events_by_month(events)
        assert len(groups) == 1
        assert groups[0]['label'] == 'Июнь 2099'
        assert len(groups[0]['events']) == 1

    def test_two_events_same_month_one_group(self):
        events = [
            {'date': '2099-06-01T19:00:00', 'event_id': 'e1'},
            {'date': '2099-06-20T20:00:00', 'event_id': 'e2'},
        ]
        groups = group_events_by_month(events)
        assert len(groups) == 1
        assert len(groups[0]['events']) == 2

    def test_two_different_months_two_groups(self):
        events = [
            {'date': '2099-06-01T19:00:00', 'event_id': 'e1'},
            {'date': '2099-07-15T20:00:00', 'event_id': 'e2'},
        ]
        groups = group_events_by_month(events)
        assert len(groups) == 2
        assert groups[0]['label'] == 'Июнь 2099'
        assert groups[1]['label'] == 'Июль 2099'

    def test_preserves_event_order(self):
        events = [
            {'date': '2099-01-10T19:00:00', 'event_id': 'e1'},
            {'date': '2099-01-20T19:00:00', 'event_id': 'e2'},
            {'date': '2099-02-05T19:00:00', 'event_id': 'e3'},
        ]
        groups = group_events_by_month(events)
        assert groups[0]['events'][0]['event_id'] == 'e1'
        assert groups[0]['events'][1]['event_id'] == 'e2'
        assert groups[1]['events'][0]['event_id'] == 'e3'


# ── collect_tags ─────────────────────────────────────────────────────────────

class TestCollectTags:
    def test_empty_returns_empty(self):
        assert collect_tags([]) == []

    def test_single_tag(self):
        events = [{'tags': ['Comedy']}]
        assert collect_tags(events) == ['Comedy']

    def test_deduplicates(self):
        events = [{'tags': ['Comedy']}, {'tags': ['Comedy', 'Music']}]
        result = collect_tags(events)
        assert result.count('Comedy') == 1
        assert 'Music' in result

    def test_preserves_first_seen_order(self):
        events = [
            {'tags': ['B', 'A']},
            {'tags': ['C', 'A']},
        ]
        result = collect_tags(events)
        assert result == ['B', 'A', 'C']

    def test_events_without_tags_key(self):
        events = [{'event_id': 'e1'}, {'tags': ['Jazz']}]
        assert collect_tags(events) == ['Jazz']


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

    def _make_site_data(self, events=None, locations=None, performers=None,
                        performer_products_map=None, products=None):
        events = events or []
        locations = locations or []
        performers = performers or []
        products = products or []
        performer_products_map = performer_products_map or {}

        performer_upcoming = {}
        performer_archive = {}
        location_events_map = {}
        for event in events:
            for pid in event.get('performer_ids', []):
                performer_upcoming.setdefault(pid, []).append(event)
            loc_id = event.get('location_id', '')
            location_events_map.setdefault(loc_id, []).append(event)

        return {
            'events': events,
            'past_events': [],
            'locations': locations,
            'performers': performers,
            'products': products,
            'performer_products_map': performer_products_map,
            'performer_upcoming': performer_upcoming,
            'performer_archive': performer_archive,
            'location_events_map': location_events_map,
        }

    def _run(self, events=None, locations=None, performers=None,
             performer_products_map=None, products=None):
        site_data = self._make_site_data(
            events=events, locations=locations, performers=performers,
            performer_products_map=performer_products_map, products=products,
        )
        generate_html_files(site_data, self.tmp, TEMPLATES_DIR)

    def _enrich(self, event):
        """Add fields that fetch_data would normally add."""
        return {**event, 'performers': []}

    def test_index_html_generated(self):
        self._run()
        assert (self.tmp / 'index.html').exists()

    def test_events_html_generated(self):
        self._run()
        assert (self.tmp / 'events.html').exists()

    def test_event_page_generated_by_id(self):
        event = self._enrich(SAMPLE_EVENT_INTERNAL)
        self._run(events=[event], locations=[SAMPLE_LOCATION])
        assert (self.tmp / 'events' / 'evt-001.html').exists()

    def test_event_slug_page_generated(self):
        event = self._enrich(SAMPLE_EVENT_INTERNAL)
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
        event = self._enrich(SAMPLE_EVENT_EXTERNAL)
        self._run(events=[event], locations=[SAMPLE_LOCATION])
        content = (self.tmp / 'events' / 'evt-002.html').read_text()
        assert 'https://example.com/tickets' in content

    def test_index_shows_external_badge(self):
        event = self._enrich(SAMPLE_EVENT_EXTERNAL)
        self._run(events=[event], locations=[SAMPLE_LOCATION])
        content = (self.tmp / 'index.html').read_text()
        assert 'ВНЕШНЕЕ' in content

    def test_checkout_html_generated(self):
        self._run()
        assert (self.tmp / 'checkout.html').exists()

    def test_processing_html_generated(self):
        self._run()
        assert (self.tmp / 'processing.html').exists()

    def test_accessibility_html_generated(self):
        self._run()
        assert (self.tmp / 'accessibility.html').exists()
