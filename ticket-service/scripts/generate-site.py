

#!/usr/bin/env python3
"""
Static Site Generator for YallaBalagan Ticket Service
Generates static HTML pages from Jinja2 templates
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Paths
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / 'frontend' / 'templates'
STATIC_DIR = BASE_DIR / 'frontend' / 'static'
OUTPUT_DIR = BASE_DIR / 'site-output'


def format_date(date_str):
    """Format date for display"""
    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    months = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
        5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
        9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }
    return f"{dt.day} {months[dt.month]} {dt.year}"


def format_time(date_str):
    """Format time for display"""
    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    return dt.strftime('%H:%M')


def create_test_data():
    """Create test data for demonstration"""

    # Test locations
    locations = [
        {
            'location_id': 'loc-1',
            'name': 'Дизенгоф Центр',
            'slug': 'dizengoff-center',
            'description': 'Культурное пространство в центре Тель-Авива с отличной акустикой и уютной атмосферой',
            'capacity': 150,
            'address': {
                'street': 'Dizengoff 50',
                'city': 'Tel Aviv',
                'coordinates': {
                    'lat': 32.0853,
                    'lng': 34.7818
                }
            },
            'parkings': [
                {
                    'type': 'underground',
                    'name': 'Подземная парковка Дизенгоф',
                    'description': '100 метров от входа, работает круглосуточно',
                    'price': '15₪/час',
                    'location': {
                        'google_maps_url': 'https://maps.google.com/?q=32.0854,34.7820'
                    }
                }
            ],
            'media': {
                'photos': [
                    'https://yallabalagan-newsletter-images.s3.eu-north-1.amazonaws.com/uploads/20251124-230605-66ccbc85.jpg'
                ]
            }
        },
        {
            'location_id': 'loc-2',
            'name': 'Ротшильд Клуб',
            'slug': 'rothschild-club',
            'description': 'Стильное пространство на бульваре Ротшильд для камерных выступлений',
            'capacity': 80,
            'address': {
                'street': 'Rothschild Boulevard 12',
                'city': 'Tel Aviv',
                'coordinates': {
                    'lat': 32.0644,
                    'lng': 34.7736
                }
            },
            'parkings': [
                {
                    'type': 'street',
                    'name': 'Уличная парковка',
                    'description': 'Бесплатная парковка вдоль бульвара',
                    'price': 'Бесплатно после 19:00'
                }
            ],
            'media': {
                'photos': [
                    'https://yallabalagan-newsletter-images.s3.eu-north-1.amazonaws.com/uploads/20251124-230618-07f9ec01.jpg'
                ]
            }
        }
    ]

    # Test events
    base_date = datetime.now() + timedelta(days=7)
    events = [
        {
            'event_id': 'evt-1',
            'title': 'Stand-up вечер с российскими комиками',
            'description': 'Яркий стендап-вечер с лучшими комиками из России и Израиля. Два часа смеха и хорошего настроения гарантированы!',
            'date': base_date.isoformat() + 'Z',
            'date_formatted': format_date(base_date.isoformat() + 'Z'),
            'time_formatted': '20:00',
            'location_id': 'loc-1',
            'location_name': 'Дизенгоф Центр',
            'status': 'active',
            'images': [
                'https://yallabalagan-newsletter-images.s3.eu-north-1.amazonaws.com/uploads/20251124-230422-ae3bbd86.png'
            ],
            'ticket_types': [
                {
                    'id': 'regular',
                    'name': 'Обычный',
                    'description': 'Стандартное место в зале',
                    'price': 120,
                    'total': 100,
                    'available': 85
                },
                {
                    'id': 'vip',
                    'name': 'VIP',
                    'description': 'Места в первых рядах + welcome drink',
                    'price': 200,
                    'total': 20,
                    'available': 12
                }
            ],
            'refund_policy': {
                'enabled': True,
                'hours_before': 48
            },
            'min_price': 120
        },
        {
            'event_id': 'evt-2',
            'title': 'Музыкальный вечер: Русский рок',
            'description': 'Трибьют-концерт легендам русского рока. Кино, ДДТ, Наутилус Помпилиус и другие хиты.',
            'date': (base_date + timedelta(days=14)).isoformat() + 'Z',
            'date_formatted': format_date((base_date + timedelta(days=14)).isoformat() + 'Z'),
            'time_formatted': '21:00',
            'location_id': 'loc-2',
            'location_name': 'Ротшильд Клуб',
            'status': 'active',
            'images': [
                'https://yallabalagan-newsletter-images.s3.eu-north-1.amazonaws.com/uploads/20251124-230433-b2131c2e.png'
            ],
            'ticket_types': [
                {
                    'id': 'regular',
                    'name': 'Обычный',
                    'price': 100,
                    'total': 80,
                    'available': 65
                }
            ],
            'refund_policy': {
                'enabled': True,
                'hours_before': 24
            },
            'min_price': 100
        },
        {
            'event_id': 'evt-3',
            'title': 'Интеллектуальная игра "Что? Где? Когда?"',
            'description': 'Классическая интеллектуальная игра в формате ЧГК. Соберите команду до 6 человек!',
            'date': (base_date + timedelta(days=21)).isoformat() + 'Z',
            'date_formatted': format_date((base_date + timedelta(days=21)).isoformat() + 'Z'),
            'time_formatted': '19:00',
            'location_id': 'loc-1',
            'location_name': 'Дизенгоф Центр',
            'status': 'active',
            'images': [
                'https://yallabalagan-newsletter-images.s3.eu-north-1.amazonaws.com/uploads/20251124-230451-a1d35d53.png'
            ],
            'ticket_types': [
                {
                    'id': 'team',
                    'name': 'Команда (6 человек)',
                    'description': 'Билет на команду из 6 человек',
                    'price': 300,
                    'total': 25,
                    'available': 18
                }
            ],
            'min_price': 300
        }
    ]

    return events, locations


def generate_site(api_url=None, use_test_data=False):
    """Generate static site from templates"""

    print("🚀 Generating YallaBalagan static site...")

    # Setup Jinja2
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    env.globals.update({
        'format_date': format_date,
        'format_time': format_time,
        'min': min,
        'max': max
    })

    # Clean output directory
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # Copy static files
    print("📁 Copying static files...")
    shutil.copytree(STATIC_DIR, OUTPUT_DIR / 'static')

    # Get data
    if use_test_data:
        print("📊 Using test data...")
        events, locations = create_test_data()
    else:
        print("📊 Fetching data from API...")
        import requests
        try:
            response = requests.get(f"{api_url}/api/events", timeout=10)
            response.raise_for_status()
            data = response.json()
            events = data.get('events', [])

            response = requests.get(f"{api_url}/api/locations", timeout=10)
            response.raise_for_status()
            data = response.json()
            locations = data.get('locations', [])

            print(f"✅ Fetched {len(events)} events and {len(locations)} locations")
        except Exception as e:
            print(f"❌ Error fetching from API: {e}")
            raise

        # Process events from API
        for event in events:
            if 'date_formatted' not in event:
                event['date_formatted'] = format_date(event['date'])
            if 'time_formatted' not in event:
                event['time_formatted'] = format_time(event['date'])
            if 'min_price' not in event and event.get('ticket_types'):
                event['min_price'] = min([t['price'] for t in event['ticket_types']])

        # Process locations
        for location in locations:
            # Ensure location has location_name for compatibility
            if 'location_name' not in location and 'name' in location:
                location['location_name'] = location['name']

    # Filter events to show only active and sold_out events on public site
    visible_events = [e for e in events if e.get('status') in ['active', 'sold_out']]
    print(f"📊 Filtered {len(visible_events)} visible events out of {len(events)} total events")

    # Create location lookup
    location_map = {loc['location_id']: loc for loc in locations}

    # Generate index.html
    print("📄 Generating index.html...")
    template = env.get_template('index.html')
    html = template.render(events=visible_events)
    (OUTPUT_DIR / 'index.html').write_text(html, encoding='utf-8')

    # Generate event detail pages
    print("📄 Generating event detail pages...")
    (OUTPUT_DIR / 'events').mkdir()
    template = env.get_template('event_detail.html')

    for event in visible_events:
        location = location_map.get(event['location_id'])
        html = template.render(event=event, location=location)
        (OUTPUT_DIR / 'events' / f"{event['event_id']}.html").write_text(html, encoding='utf-8')

        slug = event.get('slug')
        if slug:
            (OUTPUT_DIR / 'events' / f"{slug}.html").write_text(html, encoding='utf-8')

    # Generate location detail pages
    print("📄 Generating location detail pages...")
    (OUTPUT_DIR / 'locations').mkdir()
    template = env.get_template('location_detail.html')

    for location in locations:
        # Get upcoming events at this location (only visible ones)
        upcoming_events = [e for e in visible_events if e['location_id'] == location['location_id']]

        html = template.render(location=location, upcoming_events=upcoming_events)
        (OUTPUT_DIR / 'locations' / f"{location['slug']}.html").write_text(html, encoding='utf-8')

    # Generate checkout pages (examples) - only if we have visible events
    if visible_events:
        print("📄 Generating checkout page example...")
        template = env.get_template('checkout.html')
        event = visible_events[0]
        ticket_type = event['ticket_types'][0]
        html = template.render(event=event, ticket_type=ticket_type, service_fee=10)
        (OUTPUT_DIR / 'checkout.html').write_text(html, encoding='utf-8')

        # Generate order confirmation example
        print("📄 Generating order confirmation example...")
        template = env.get_template('order_confirmation.html')
        order = {
            'order_id': 'ORD-2025-DEMO-001',
            'customer': {
                'name': 'Иван Иванов',
                'email': 'ivan@example.com',
                'phone': '+972-50-123-4567'
            },
            'tickets': [{
                'type_name': 'Обычный',
                'quantity': 2,
                'price_per_ticket': 120
            }],
            'total_amount': 240,
            'payment': {
                'status': 'completed',
                'allpay_transaction_id': 'TXN-123456'
            },
            'qr_codes': [
                {'code': 'YBEV-2025-0001-1', 'ticket_type': 'Обычный'},
                {'code': 'YBEV-2025-0001-2', 'ticket_type': 'Обычный'}
            ]
        }
        html = template.render(order=order, event=visible_events[0])
        (OUTPUT_DIR / 'order-example.html').write_text(html, encoding='utf-8')

    print(f"\n✅ Site generated successfully!")
    print(f"📂 Output directory: {OUTPUT_DIR}")
    print(f"📊 Generated:")
    print(f"   - 1 index page")
    extra_event_pages = sum(1 for event in visible_events if event.get('slug'))
    total_event_pages = len(visible_events) + extra_event_pages
    print(f"   - {total_event_pages} event pages (включая {extra_event_pages} дополнительных slug-страниц)")
    print(f"   - {len(locations)} location pages")
    example_pages = 2 if visible_events else 0
    if example_pages > 0:
        print(f"   - {example_pages} example pages (checkout, order)")
    print(f"\n🌐 Open {OUTPUT_DIR}/index.html in your browser to preview")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Generate YallaBalagan static site')
    parser.add_argument('--api-url', help='API URL to fetch real data')
    parser.add_argument('--no-test-data', action='store_true', help='Use API instead of test data')

    args = parser.parse_args()

    # Use API URL from args, environment, or default
    api_url = args.api_url or os.environ.get('API_URL') or 'https://ovajavet67.execute-api.eu-north-1.amazonaws.com'

    generate_site(
        api_url=api_url,
        use_test_data=not args.no_test_data
    )
