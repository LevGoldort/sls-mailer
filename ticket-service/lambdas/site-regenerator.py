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

s3_client = boto3.client('s3')
API_URL = os.environ.get('API_URL', 'https://ovajavet67.execute-api.eu-north-1.amazonaws.com')
S3_BUCKET = os.environ.get('S3_BUCKET', 'yallabalagan-tickets-frontend')
REGION = os.environ.get('AWS_REGION', 'eu-north-1')

def format_date(date_str):
    """Format date for display"""
    # Parse as naive datetime (already in Israel time)
    clean_str = date_str.replace('Z', '')
    dt = datetime.fromisoformat(clean_str)
    months = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
        5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
        9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }
    return f"{dt.day} {months[dt.month]} {dt.year}"

def format_time(date_str):
    """Format time for display"""
    # Parse as naive datetime (already in Israel time)
    clean_str = date_str.replace('Z', '')
    dt = datetime.fromisoformat(clean_str)
    return dt.strftime('%H:%M')

def generate_sitemap(events, locations):
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

def fetch_data():
    """Fetch events and locations from API"""
    import requests
    print(f"Fetching data from {API_URL}")

    # Fetch events
    response = requests.get(f"{API_URL}/api/events", timeout=10)
    response.raise_for_status()
    all_events = response.json().get('events', [])

    # Filter out past events (event_date + 1 hour < now)
    events = [event for event in all_events if not is_event_past(event['date'])]

    filtered_count = len(all_events) - len(events)
    if filtered_count > 0:
        print(f"Filtered out {filtered_count} past events")

    # Process events
    for event in events:
        if 'date_formatted' not in event:
            event['date_formatted'] = format_date(event['date'])
        if 'time_formatted' not in event:
            event['time_formatted'] = format_time(event['date'])
        if 'min_price' not in event and event.get('ticket_types'):
            event['min_price'] = min([t['price'] for t in event['ticket_types']])

    # Fetch locations
    response = requests.get(f"{API_URL}/api/locations", timeout=10)
    response.raise_for_status()
    locations = response.json().get('locations', [])

    print(f"Fetched {len(events)} upcoming events and {len(locations)} locations")
    return events, locations

def generate_html_files(events, locations, output_dir, templates_dir):
    """Generate HTML files from templates"""
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    env.globals.update({
        'format_date': format_date,
        'format_time': format_time,
        'min': min,
        'max': max,
        'fb_pixel_id': os.environ.get('FB_PIXEL_ID'),
        'ga4_id': os.environ.get('GA4_ID'),
        'api_url': API_URL
    })

    # Create location lookup
    location_map = {loc['location_id']: loc for loc in locations}

    # Generate index.html
    print("Generating index.html...")
    template = env.get_template('index.html')
    html = template.render(events=events)
    (output_dir / 'index.html').write_text(html, encoding='utf-8')

    # Generate event detail pages
    print("Generating event detail pages...")
    (output_dir / 'events').mkdir(exist_ok=True)
    template = env.get_template('event_detail.html')

    for event in events:
        location = location_map.get(event['location_id'])
        html = template.render(event=event, location=location)
        event_filename = output_dir / 'events' / f"{event['event_id']}.html"
        event_filename.write_text(html, encoding='utf-8')

        slug = event.get('slug')
        if slug:
            slug_filename = output_dir / 'events' / f"{slug}.html"
            slug_filename.write_text(html, encoding='utf-8')

    # Generate location detail pages
    print("Generating location detail pages...")
    (output_dir / 'locations').mkdir(exist_ok=True)
    template = env.get_template('location_detail.html')

    for location in locations:
        upcoming_events = [e for e in events if e['location_id'] == location['location_id']]
        html = template.render(location=location, upcoming_events=upcoming_events)
        slug = location.get('slug', location['location_id'])
        (output_dir / 'locations' / f"{slug}.html").write_text(html, encoding='utf-8')

    # Generate processing.html (payment processing page)
    print("Generating processing.html...")
    template = env.get_template('processing.html')
    html = template.render()
    (output_dir / 'processing.html').write_text(html, encoding='utf-8')

    # Generate checkout.html (checkout page)
    print("Generating checkout.html...")
    template = env.get_template('checkout.html')
    html = template.render()
    (output_dir / 'checkout.html').write_text(html, encoding='utf-8')

    # Generate ticket.html (public ticket view, JS-driven)
    print("Generating ticket.html...")
    template = env.get_template('ticket.html')
    html = template.render()
    (output_dir / 'ticket.html').write_text(html, encoding='utf-8')

    # Generate accessibility.html
    print("Generating accessibility.html...")
    template = env.get_template('accessibility.html')
    html = template.render()
    (output_dir / 'accessibility.html').write_text(html, encoding='utf-8')

    # Generate mock_payment.html (if in mock mode)
    payment_mode = os.environ.get('PAYMENT_MODE', 'mock').lower()
    slugged_events = sum(1 for event in events if event.get('slug'))
    pages_generated = 1 + len(events) + slugged_events + len(locations) + 4  # +4 for processing.html, checkout.html, ticket.html, accessibility.html

    if payment_mode == 'mock':
        print("Generating mock_payment.html...")
        template = env.get_template('mock_payment.html')
        html = template.render()
        (output_dir / 'mock_payment.html').write_text(html, encoding='utf-8')
        pages_generated += 1

    # Generate sitemap.xml
    print("Generating sitemap.xml...")
    sitemap = generate_sitemap(events, locations)
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
        events, locations = fetch_data()

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
        generate_html_files(events, locations, output_dir, templates_dir)

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
