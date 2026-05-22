#!/usr/bin/env python3
"""
Lambda function to regenerate static site and deploy to S3
Triggered from admin panel via API Gateway
"""
import os
import json
import boto3
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

from utils.date_helpers import (
    date_num, month_abbr, month_full, day_of_week,
    format_date_full, format_time, year, ru_plural,
)
from utils.ui_strings import UI_STRINGS

s3_client = boto3.client('s3')
API_URL = os.environ.get('API_URL', 'https://ovajavet67.execute-api.eu-north-1.amazonaws.com')
S3_BUCKET = os.environ.get('S3_BUCKET', 'yallabalagan-tickets-frontend')
REGION = os.environ.get('AWS_REGION', 'eu-north-1')

def generate_sitemap(events, locations, performers=None):
    """Generate sitemap.xml"""
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom

    urlset = Element('urlset', xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    # Homepage
    url = SubElement(urlset, 'url')
    SubElement(url, 'loc').text = 'https://yallabalagan.org/'
    SubElement(url, 'changefreq').text = 'daily'
    SubElement(url, 'priority').text = '1.0'

    # Static pages
    for page in ['accessibility.html']:
        url = SubElement(urlset, 'url')
        SubElement(url, 'loc').text = f'https://yallabalagan.org/{page}'
        SubElement(url, 'changefreq').text = 'monthly'
        SubElement(url, 'priority').text = '0.5'

    # Events
    for event in events:
        url = SubElement(urlset, 'url')
        SubElement(url, 'loc').text = f"https://yallabalagan.org/events/{event['event_id']}.html"
        SubElement(url, 'changefreq').text = 'weekly'
        SubElement(url, 'priority').text = '0.8'

    # Locations
    for location in locations:
        url = SubElement(urlset, 'url')
        slug = location.get('slug', location['location_id'])
        SubElement(url, 'loc').text = f"https://yallabalagan.org/locations/{slug}.html"
        SubElement(url, 'changefreq').text = 'monthly'
        SubElement(url, 'priority').text = '0.6'

    # Performers
    for performer in (performers or []):
        if performer.get('slug'):
            url = SubElement(urlset, 'url')
            SubElement(url, 'loc').text = f"https://yallabalagan.org/performer/{performer['slug']}/"
            SubElement(url, 'changefreq').text = 'weekly'
            SubElement(url, 'priority').text = '0.7'

    # Pretty print
    xml_str = minidom.parseString(tostring(urlset)).toprettyxml(indent="  ")
    return xml_str

def is_event_past(event_date_str):
    """Check if event is past (event_date + 30 minutes < now)"""
    import pytz
    from datetime import timedelta

    # Parse as naive datetime, then localize to Israel timezone
    clean_str = event_date_str.replace('Z', '')
    naive_dt = datetime.fromisoformat(clean_str)
    israel_tz = pytz.timezone('Asia/Jerusalem')
    event_dt = israel_tz.localize(naive_dt)
    event_end_time = event_dt + timedelta(minutes=30)  # Fixed: 30 minutes
    now = datetime.now(israel_tz)
    return event_end_time <= now

_MONTHS_NOM = {
    1:'Январь', 2:'Февраль', 3:'Март', 4:'Апрель', 5:'Май', 6:'Июнь',
    7:'Июль', 8:'Август', 9:'Сентябрь', 10:'Октябрь', 11:'Ноябрь', 12:'Декабрь',
}

def group_events_by_month(events):
    """Return [{label, events}] grouped by calendar month, preserving order."""
    groups = []
    current_key = None
    for event in events:
        clean = event['date'].replace('Z', '').split('+')[0]
        dt = datetime.fromisoformat(clean)
        key = event['date'][:7]
        if key != current_key:
            current_key = key
            label = f"{_MONTHS_NOM[dt.month]} {dt.year}"
            groups.append({'label': label, 'events': []})
        groups[-1]['events'].append(event)
    return groups


def collect_tags(events):
    """Return list of unique tags across all events, preserving first-seen order."""
    seen = set()
    tags = []
    for event in events:
        for tag in event.get('tags', []):
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags


def _enrich_event(event, performer_map):
    """Add computed display fields to an event dict (in-place)."""
    if 'date_formatted' not in event:
        event['date_formatted'] = format_date_full(event['date'])
    if 'time_formatted' not in event:
        event['time_formatted'] = format_time(event['date'])
    if 'min_price' not in event and event.get('event_type', 'internal') == 'internal' and event.get('ticket_types'):
        event['min_price'] = min(t['price'] for t in event['ticket_types'])
    event_performer_ids = event.get('performer_ids', [])
    event['performers'] = [performer_map[pid] for pid in event_performer_ids if pid in performer_map]


def fetch_data():
    """Fetch all site data and return a SiteData dict."""
    import requests
    print(f"Fetching data from {API_URL}")

    # Events (all — upcoming filtered separately; both needed for archive)
    response = requests.get(f"{API_URL}/api/events", timeout=10)
    response.raise_for_status()
    all_events_raw = response.json().get('events', [])

    upcoming_events = [e for e in all_events_raw if not is_event_past(e['date'])]
    past_events = [e for e in all_events_raw if is_event_past(e['date'])]
    filtered_count = len(past_events)
    if filtered_count:
        print(f"Filtered out {filtered_count} past events (kept for archive)")

    # Locations
    response = requests.get(f"{API_URL}/api/locations", timeout=10)
    response.raise_for_status()
    locations = response.json().get('locations', [])

    # Performers (non-fatal)
    performers = []
    try:
        response = requests.get(f"{API_URL}/api/performers", timeout=10)
        response.raise_for_status()
        performers = response.json().get('performers', [])
    except Exception as e:
        print(f"Warning: could not fetch performers: {e}")

    # Products (non-fatal)
    products = []
    try:
        response = requests.get(f"{API_URL}/api/products", timeout=10)
        response.raise_for_status()
        products = response.json().get('products', [])
    except Exception as e:
        print(f"Warning: could not fetch products: {e}")

    performer_map = {p['performer_id']: p for p in performers}

    # Enrich all events with display fields + performer objects
    for event in upcoming_events + past_events:
        _enrich_event(event, performer_map)

    # performer_id → upcoming events (asc by date)
    performer_upcoming = {}
    for event in sorted(upcoming_events, key=lambda e: e['date']):
        for pid in event.get('performer_ids', []):
            performer_upcoming.setdefault(pid, []).append(event)

    # performer_id → past events (desc by date)
    performer_archive = {}
    for event in sorted(past_events, key=lambda e: e['date'], reverse=True):
        for pid in event.get('performer_ids', []):
            performer_archive.setdefault(pid, []).append(event)

    # performer_id → products
    performer_products_map = {}
    for product in products:
        performer_products_map.setdefault(product['performer_id'], []).append(product)

    # location_id → upcoming events (asc by date)
    location_events_map = {}
    for event in sorted(upcoming_events, key=lambda e: e['date']):
        location_events_map.setdefault(event['location_id'], []).append(event)

    # Shows (non-fatal)
    shows = []
    try:
        response = requests.get(f"{API_URL}/api/shows", timeout=10)
        response.raise_for_status()
        shows = response.json().get('shows', [])
    except Exception as e:
        print(f"Warning: could not fetch shows: {e}")

    # Episodes (non-fatal)
    episodes = []
    try:
        response = requests.get(f"{API_URL}/api/episodes", timeout=10)
        response.raise_for_status()
        episodes = response.json().get('episodes', [])
    except Exception as e:
        print(f"Warning: could not fetch episodes: {e}")

    # show_id → sorted episodes
    show_episodes_map = {}
    for ep in sorted(episodes, key=lambda e: e.get('number', 0)):
        show_episodes_map.setdefault(ep['show_id'], []).append(ep)

    # show_id → episode count
    show_episode_counts = {sid: len(eps) for sid, eps in show_episodes_map.items()}

    print(f"Fetched {len(upcoming_events)} upcoming + {len(past_events)} past events, "
          f"{len(locations)} locations, {len(performers)} performers, {len(products)} products, "
          f"{len(shows)} shows, {len(episodes)} episodes")

    return {
        'events': upcoming_events,
        'past_events': past_events,
        'locations': locations,
        'performers': performers,
        'products': products,
        'performer_products_map': performer_products_map,
        'performer_upcoming': performer_upcoming,
        'performer_archive': performer_archive,
        'location_events_map': location_events_map,
        'shows': shows,
        'episodes': episodes,
        'show_episodes_map': show_episodes_map,
        'show_episode_counts': show_episode_counts,
    }

def generate_html_files(site_data, output_dir, templates_dir):
    """Generate HTML files from templates"""
    events = site_data['events']
    locations = site_data['locations']
    performers = site_data['performers']
    products = site_data['products']
    performer_products_map = site_data['performer_products_map']
    performer_upcoming = site_data['performer_upcoming']
    performer_archive = site_data['performer_archive']
    location_events_map = site_data['location_events_map']
    shows = site_data.get('shows', [])
    episodes = site_data.get('episodes', [])
    show_episodes_map = site_data.get('show_episodes_map', {})
    show_episode_counts = site_data.get('show_episode_counts', {})

    strings = UI_STRINGS['ru']

    # Create lookup maps (must be before env.globals so they can be referenced in templates)
    location_map = {loc['location_id']: loc for loc in locations}

    _placeholder_images = [
        '/static/placeholders/5.1.png',
        '/static/placeholders/5.1-1.png',
        '/static/placeholders/5.2.png',
        '/static/placeholders/5.2-1.png',
        '/static/placeholders/5.5.png',
        '/static/placeholders/5.6.png',
        '/static/placeholders/5.6-1.png',
    ]

    def pick_placeholder(id_str):
        return _placeholder_images[hash(str(id_str)) % len(_placeholder_images)]

    env = Environment(loader=FileSystemLoader(str(templates_dir)))

    # Date filters
    env.filters['date_num'] = date_num
    env.filters['month_abbr'] = month_abbr
    env.filters['month_full'] = month_full
    env.filters['day_of_week'] = day_of_week
    env.filters['format_date'] = format_date_full
    env.filters['format_time'] = format_time
    env.filters['year'] = year

    # Globals available in every template
    env.globals.update({
        'strings': strings,
        'ru_plural': ru_plural,
        'min': min,
        'max': max,
        'fb_pixel_id': os.environ.get('FB_PIXEL_ID'),
        'ga4_id': os.environ.get('GA4_ID'),
        'api_url': API_URL,
        'location_map': location_map,
        'pick_placeholder': pick_placeholder,
    })

    pages_generated = 0

    # Generate index.html
    print("Generating index.html...")
    template = env.get_template('pages/index.html')
    html = template.render(events=events, active_nav='home')
    (output_dir / 'index.html').write_text(html, encoding='utf-8')
    pages_generated += 1

    # Generate events listing page
    print("Generating events.html...")
    template = env.get_template('pages/events.html')
    html = template.render(
        events=events,
        events_by_month=group_events_by_month(events),
        all_tags=collect_tags(events),
        active_nav='events',
    )
    (output_dir / 'events.html').write_text(html, encoding='utf-8')
    pages_generated += 1

    # Generate event detail pages
    print("Generating event detail pages...")
    (output_dir / 'events').mkdir(exist_ok=True)
    template = env.get_template('pages/event_detail.html')

    for event in events:
        location = location_map.get(event['location_id'])
        # event['performers'] is already enriched in fetch_data; attach their products
        event_performers_with_products = [
            {**p, 'products': performer_products_map.get(p['performer_id'], [])}
            for p in event.get('performers', [])
        ]
        html = template.render(
            event=event,
            location=location,
            event_performers=event_performers_with_products,
            active_nav='events',
        )
        event_filename = output_dir / 'events' / f"{event['event_id']}.html"
        event_filename.write_text(html, encoding='utf-8')
        pages_generated += 1

        slug = event.get('slug')
        if slug:
            slug_filename = output_dir / 'events' / f"{slug}.html"
            slug_filename.write_text(html, encoding='utf-8')
            pages_generated += 1

    # Generate seat picker pages for seated events
    print("Generating seat picker pages...")
    (output_dir / 'seats').mkdir(exist_ok=True)
    seats_template = env.get_template('pages/seats.html')

    for event in events:
        location = location_map.get(event.get('location_id', ''))
        if not location:
            continue
        if location.get('venue_config', {}).get('venue_type') != 'seated':
            continue
        html = seats_template.render(event=event, location=location, active_nav='events')
        slug = event.get('slug', event['event_id'])
        (output_dir / 'seats' / f"{slug}.html").write_text(html, encoding='utf-8')
        pages_generated += 1

    # Generate location detail pages
    print("Generating location detail pages...")
    (output_dir / 'locations').mkdir(exist_ok=True)
    template = env.get_template('pages/location_detail.html')

    for location in locations:
        loc_events = location_events_map.get(location['location_id'], [])
        html = template.render(location=location, upcoming_events=loc_events, active_nav='')
        slug = location.get('slug', location['location_id'])
        (output_dir / 'locations' / f"{slug}.html").write_text(html, encoding='utf-8')
        pages_generated += 1

    # Generate products listing page + detail pages
    if products:
        performer_map = {p['performer_id']: p for p in performers}

        print("Generating products.html...")
        template = env.get_template('pages/products.html')
        html = template.render(products=products, active_nav='')
        (output_dir / 'products.html').write_text(html, encoding='utf-8')
        pages_generated += 1

        print(f"Generating {len(products)} product pages...")
        (output_dir / 'products').mkdir(exist_ok=True)
        product_template = env.get_template('pages/product_detail.html')
        for product in products:
            slug = product.get('slug', product['product_id'])
            performer = performer_map.get(product.get('performer_id'))
            other = [p for p in products if p['product_id'] != product['product_id']]
            html = product_template.render(
                product=product,
                performer=performer,
                other_products=other,
                active_nav='',
            )
            (output_dir / 'products' / f"{slug}.html").write_text(html, encoding='utf-8')
            pages_generated += 1

    # Generate performers listing page
    if performers:
        print("Generating performers.html...")
        all_performer_tags = collect_tags(
            [{'tags': p.get('tags', [])} for p in performers]
        )
        template = env.get_template('pages/performers.html')
        html = template.render(
            performers=performers,
            all_tags=all_performer_tags,
            active_nav='performers',
        )
        (output_dir / 'performers.html').write_text(html, encoding='utf-8')
        pages_generated += 1

    # Generate performer detail pages
    if performers:
        print(f"Generating {len(performers)} performer pages...")
        (output_dir / 'performer').mkdir(exist_ok=True)
        performer_template = env.get_template('pages/performer_detail.html')

        for performer in performers:
            slug = performer.get('slug')
            if not slug:
                continue
            pid = performer['performer_id']
            html = performer_template.render(
                performer=performer,
                products=performer_products_map.get(pid, []),
                upcoming_events=performer_upcoming.get(pid, []),
                archive_events=performer_archive.get(pid, []),
                active_nav='performers',
            )
            performer_dir = output_dir / 'performer' / slug
            performer_dir.mkdir(exist_ok=True)
            (performer_dir / 'index.html').write_text(html, encoding='utf-8')
            pages_generated += 1

    # Generate processing.html (payment processing page)
    print("Generating processing.html...")
    template = env.get_template('pages/processing.html')
    html = template.render()
    (output_dir / 'processing.html').write_text(html, encoding='utf-8')
    pages_generated += 1

    # Generate checkout.html (checkout page)
    print("Generating checkout.html...")
    template = env.get_template('pages/checkout.html')
    html = template.render()
    (output_dir / 'checkout.html').write_text(html, encoding='utf-8')
    pages_generated += 1

    # Generate accessibility.html
    print("Generating accessibility.html...")
    template = env.get_template('pages/accessibility.html')
    html = template.render()
    (output_dir / 'accessibility.html').write_text(html, encoding='utf-8')
    pages_generated += 1

    # Generate mock_payment.html (if in mock mode)
    payment_mode = os.environ.get('PAYMENT_MODE', 'mock').lower()

    if payment_mode == 'mock':
        print("Generating mock_payment.html...")
        template = env.get_template('pages/mock_payment.html')
        html = template.render()
        (output_dir / 'mock_payment.html').write_text(html, encoding='utf-8')
        pages_generated += 1

    # Generate shows listing + detail + episode detail pages
    performer_map = {p['performer_id']: p for p in performers}

    print("Generating shows.html...")
    template = env.get_template('pages/shows.html')
    html = template.render(
        shows=shows,
        show_episode_counts=show_episode_counts,
        active_nav='',
    )
    (output_dir / 'shows.html').write_text(html, encoding='utf-8')
    pages_generated += 1

    if shows or episodes:
        print(f"Generating {len(shows)} show pages...")
        (output_dir / 'shows').mkdir(exist_ok=True)
        show_template = env.get_template('pages/show_detail.html')
        for show in shows:
            slug = show.get('slug')
            if not slug:
                continue
            ep_list = show_episodes_map.get(show['show_id'], [])
            html = show_template.render(
                show=show,
                episodes=ep_list,
                performer_map=performer_map,
                active_nav='',
            )
            (output_dir / 'shows' / f"{slug}.html").write_text(html, encoding='utf-8')
            pages_generated += 1

        print(f"Generating {len(episodes)} episode pages...")
        (output_dir / 'episodes').mkdir(exist_ok=True)
        show_map = {s['show_id']: s for s in shows}
        episode_template = env.get_template('pages/episode_detail.html')
        for ep in episodes:
            slug = ep.get('slug')
            if not slug:
                continue
            show = show_map.get(ep['show_id'], {})
            ep_performers = [performer_map[pid] for pid in ep.get('performer_ids', []) if pid in performer_map]
            html = episode_template.render(
                episode=ep,
                show=show,
                performers=ep_performers,
                active_nav='',
            )
            (output_dir / 'episodes' / f"{slug}.html").write_text(html, encoding='utf-8')
            pages_generated += 1

    # Generate sitemap.xml
    print("Generating sitemap.xml...")
    sitemap = generate_sitemap(events, locations, performers)
    (output_dir / 'sitemap.xml').write_text(sitemap, encoding='utf-8')

    print(f"Generated {pages_generated} HTML pages + sitemap.xml")

def upload_to_s3(local_dir):
    """Upload generated files to S3 bucket"""
    print(f"Uploading to S3 bucket: {S3_BUCKET}")
    uploaded_count = 0

    for root, dirs, files in os.walk(local_dir):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, local_dir)
            s3_key = relative_path

            # Determine content type
            # ВАЖНО: для HTML файлов ВСЕГДА указываем charset=utf-8 для правильного отображения русского текста
            content_type = 'text/html; charset=utf-8'
            if file.endswith('.css'):
                content_type = 'text/css; charset=utf-8'
            elif file.endswith('.js'):
                content_type = 'application/javascript; charset=utf-8'
            elif file.endswith('.xml'):
                content_type = 'application/xml; charset=utf-8'
            elif file.endswith('.txt'):
                content_type = 'text/plain; charset=utf-8'
            elif file.endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif file.endswith('.png'):
                content_type = 'image/png'

            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=open(local_path, 'rb'),
                ContentType=content_type,
                CacheControl='max-age=300'
            )
            uploaded_count += 1

    print(f"Uploaded {uploaded_count} files to S3")
    return uploaded_count

def lambda_handler(event, context):
    """Main Lambda handler"""
    try:
        print("Starting site regeneration...")
        start_time = datetime.now()

        # 1. Fetch data from API
        site_data = fetch_data()
        events = site_data['events']
        locations = site_data['locations']
        performers = site_data['performers']

        # 2. Setup directories
        temp_dir = Path(tempfile.mkdtemp())
        output_dir = temp_dir / 'output'
        output_dir.mkdir()

        # Templates and static files are bundled in /opt/templates and /opt/static
        # (via Lambda Layer)
        templates_dir = Path('/opt/templates')
        static_dir = Path('/opt/static')

        # Copy static files
        print("Copying static files...")
        print(f"Checking for static directory: {static_dir}")
        print(f"Static dir exists: {static_dir.exists()}, is_dir: {static_dir.is_dir()}")

        if not static_dir.exists():
            print(f"WARNING: {static_dir} does not exist!")
            print(f"/opt contents: {os.listdir('/opt')}")
            # Create empty static directory structure
            (output_dir / 'static').mkdir()
            (output_dir / 'static' / 'css').mkdir()
            (output_dir / 'static' / 'js').mkdir()
        else:
            shutil.copytree(static_dir, output_dir / 'static')

        # Copy robots.txt if it exists
        robots_txt = static_dir / 'robots.txt'
        if robots_txt.exists():
            print("Copying robots.txt...")
            shutil.copy(robots_txt, output_dir / 'robots.txt')
        else:
            print("WARNING: robots.txt not found in static directory")

        # 3. Generate HTML
        generate_html_files(site_data, output_dir, templates_dir)

        # 4. Upload to S3
        uploaded_count = upload_to_s3(output_dir)

        # 5. Cleanup
        shutil.rmtree(temp_dir)

        # 6. Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        site_url = f"http://{S3_BUCKET}.s3-website.{REGION}.amazonaws.com/"

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'success',
                'message': f'Site regenerated successfully in {duration:.2f}s',
                'url': site_url,
                'events_count': len(events),
                'locations_count': len(locations),
                'performers_count': len(performers),
                'files_uploaded': uploaded_count,
                'timestamp': datetime.now().isoformat()
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'error',
                'message': str(e)
            })
        }
