import json
import os
import requests
from datetime import datetime
import boto3
from collections import defaultdict

NOTION_TOKEN = os.environ['NOTION_TOKEN']
NOTION_DATABASE_ID = os.environ['NOTION_DATABASE_ID']
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
YOUTUBE_PLAYLIST_ID = os.environ.get('YOUTUBE_PLAYLIST_ID', '')

s3_client = boto3.client('s3')

# Contact info
CONTACT_EMAIL = "yalla@yallabalagan.org"
CONTACT_PHONE = "+972506491680"
CONTACT_ADDRESS = "Bat Yam, Rothschild 17"


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def get_latest_video_from_playlist(api_key, playlist_id):
    """
    Получает информацию о последнем видео из YouTube плейлиста
    """
    if not api_key or not playlist_id:
        print("YouTube API Key или Playlist ID не заданы")
        return None

    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    params = {
        'part': 'snippet',
        'playlistId': playlist_id,
        'maxResults': 1,
        'key': api_key
    }

    try:
        print(f"Запрос к YouTube API для плейлиста: {playlist_id}")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        if 'items' in data and len(data['items']) > 0:
            video_id = data['items'][0]['snippet']['resourceId']['videoId']
            video_title = data['items'][0]['snippet']['title']
            print(f"Получено последнее видео: {video_title} (ID: {video_id})")

            return {
                'video_id': video_id,
                'title': video_title
            }
        else:
            print("Плейлист пуст или видео не найдены")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к YouTube API: {str(e)}")
        return None
    except Exception as e:
        print(f"Неожиданная ошибка при получении видео: {str(e)}")
        return None


def get_all_events():
    """Получает все активные события из Notion"""
    response = requests.post(
        f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query",
        headers=notion_headers(),
        json={
            "sorts": [
                {
                    "property": "Date",
                    "direction": "ascending"
                }
            ]
        }
    )

    if response.status_code != 200:
        print(f"Error fetching events: {response.text}")
        return []

    pages = response.json().get('results', [])
    events = []

    for page in pages:
        props = page['properties']

        title_prop = props.get('Name', {}).get('title', [])
        title = title_prop[0]['text']['content'] if title_prop else 'Без названия'

        date_prop = props.get('Date', {}).get('date')
        date = date_prop.get('start') if date_prop else None

        url = props.get('URL', {}).get('url', '')

        cover = page.get('cover')
        image_url = None
        if cover:
            if cover['type'] == 'external':
                image_url = cover['external']['url']
            elif cover['type'] == 'file':
                image_url = cover['file']['url']

        if date and url:
            events.append({
                'title': title,
                'date': date,
                'url': url,
                'image': image_url
            })

    print(f"Found {len(events)} events")
    return events


def group_events_by_month(events):
    """Группирует события по месяцам"""
    grouped = defaultdict(list)

    for event in events:
        try:
            date_obj = datetime.fromisoformat(event['date'])
            month_key = f"{date_obj.year}-{date_obj.month:02d}"
            grouped[month_key].append(event)
        except:
            continue

    return dict(sorted(grouped.items()))


def generate_footer_html():
    """Генерирует HTML футера с контактами"""
    return f"""
                <div class="footer-contacts">
                    <h3>Contact Us</h3>
                    <div class="contact-item">
                        <span class="contact-icon">📧</span>
                        <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
                    </div>
                    <div class="contact-item">
                        <span class="contact-icon">📱</span>
                        <a href="https://wa.me/{CONTACT_PHONE.replace('+', '')}" target="_blank">{CONTACT_PHONE}</a>
                    </div>
                    <div class="contact-item">
                        <span class="contact-icon">📍</span>
                        <span>{CONTACT_ADDRESS}</span>
                    </div>
                    <div class="footer-links">
                        <a href="/privacy">Privacy Policy</a>
                        <span class="separator">•</span>
                        <a href="/terms">Terms & Conditions</a>
                    </div>
                </div>
    """


def generate_footer_styles():
    """Генерирует CSS для футера"""
    return """
            .footer-contacts {
                margin-top: 30px;
                padding-top: 25px;
                border-top: 2px solid #e2e8f0;
            }

            .footer-contacts h3 {
                font-size: 18px;
                margin-bottom: 15px;
                color: #1a202c;
            }

            .contact-item {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 10px;
                color: #4a5568;
                font-size: 14px;
            }

            .contact-icon {
                font-size: 16px;
                width: 20px;
            }

            .contact-item a {
                color: #4a5568;
                text-decoration: none;
                transition: color 0.2s;
            }

            .contact-item a:hover {
                color: #e535ab;
            }

            .footer-links {
                margin-top: 15px;
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 13px;
            }

            .footer-links a {
                color: #718096;
                text-decoration: none;
                transition: color 0.2s;
            }

            .footer-links a:hover {
                color: #e535ab;
            }

            .footer-links .separator {
                color: #cbd5e0;
            }
    """


def generate_html(events, youtube_video=None):
    """Генерирует HTML страницу с событиями"""

    months_ru = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }

    def format_date(date_str):
        try:
            date_obj = datetime.fromisoformat(date_str)
            months_ru_genitive = {
                1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
                5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
                9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
            }
            return f"{date_obj.day} {months_ru_genitive[date_obj.month]}"
        except:
            return date_str

    def format_month_header(month_key):
        try:
            year, month = month_key.split('-')
            return f"{months_ru[int(month)]} {year}"
        except:
            return month_key

    # Генерируем HTML для блока подкаста (если есть данные)
    podcast_html = ""
    if youtube_video and youtube_video.get('video_id') and youtube_video.get('title'):
        video_id = youtube_video['video_id']
        video_title = youtube_video['title']
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        podcast_html = f"""
                <div class="podcast-link-block">
                    <p class="podcast-intro">У нас каждую неделю выходит подкаст "Че там у евреев"!</p>
                    <p class="podcast-latest">Последний выпуск:</p>
                    <a href="{video_url}" target="_blank" class="podcast-link">
                        🎙️ {video_title}
                    </a>
                </div>
        """

    # Группируем события по месяцам
    grouped_events = group_events_by_month(events)

    events_html = ""

    if grouped_events:
        for month_key, month_events in grouped_events.items():
            events_html += f'<div class="month-section"><h2 class="month-header">{format_month_header(month_key)}</h2><div class="events-grid">'

            for event in month_events:
                # Используем дефолтную картинку если у события нет своей
                event_image = event['image'] if event[
                    'image'] else 'https://events-site-yallabalagan.s3.eu-north-1.amazonaws.com/images/yalla_square.jpg'
                image_html = f'<div class="event-image"><img src="{event_image}" alt="{event["title"]}"></div>'

                # Экранируем данные для использования в JavaScript
                title_escaped = event['title'].replace("'", "\\'").replace('"', '\\"')
                url_escaped = event['url'].replace("'", "\\'")

                events_html += f"""
                <div class="event-card-wrapper">
                    <div class="event-card">
                        <a href="{event['url']}" class="event-link" target="_blank" rel="noopener">
                            {image_html}
                            <div class="event-info">
                                <div class="event-date">{format_date(event['date'])}</div>
                                <h3 class="event-title">{event['title']}</h3>
                            </div>
                        </a>
                        <div class="calendar-button-container">
                            <button class="add-to-calendar-btn" onclick="toggleCalendarMenu(event, this)" data-event-title="{title_escaped}" data-event-date="{event['date']}" data-event-url="{url_escaped}">
                                <span class="calendar-icon">📅</span>
                                <span>Добавить в календарь</span>
                                <span class="dropdown-arrow">▼</span>
                            </button>
                            <div class="calendar-dropdown">
                                <a href="#" class="calendar-option" onclick="addToGoogleCalendar(event, this.closest('.calendar-button-container'))">
                                    <span class="calendar-service-icon">🔵</span> Google Calendar
                                </a>
                                <a href="#" class="calendar-option" onclick="addToAppleCalendar(event, this.closest('.calendar-button-container'))">
                                    <span class="calendar-service-icon">🍎</span> Apple Calendar
                                </a>
                                <a href="#" class="calendar-option" onclick="addToOutlook(event, this.closest('.calendar-button-container'))">
                                    <span class="calendar-service-icon">📧</span> Outlook
                                </a>
                                <a href="#" class="calendar-option" onclick="addToYahoo(event, this.closest('.calendar-button-container'))">
                                    <span class="calendar-service-icon">🟣</span> Yahoo
                                </a>
                                <a href="#" class="calendar-option" onclick="downloadICS(event, this.closest('.calendar-button-container'))">
                                    <span class="calendar-service-icon">📥</span> Скачать ICS
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
                """

            events_html += '</div></div>'
    else:
        events_html = '<div class="no-events"><h2>Пока нет событий</h2><p>Следите за обновлениями в соцсетях!</p></div>'

    footer_html = generate_footer_html()
    footer_styles = generate_footer_styles()

    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ялла, Балаган! - Ближайшие события</title>

        <!-- Open Graph / Facebook -->
        <meta property="og:type" content="website">
        <meta property="og:url" content="https://yallabalagan.org/">
        <meta property="og:title" content="Ялла, Балаган!">
        <meta property="og:description" content="Мероприятия связанные с комедией и юмором в Израиле. Подкаст 'Че там у евреев', шоу 'Изотоп Комедия' и многое другое!">
        <meta property="og:image" content="https://events-site-yallabalagan.s3.eu-north-1.amazonaws.com/images/yalla_square.jpg">

        <!-- Twitter -->
        <meta property="twitter:card" content="summary_large_image">
        <meta property="twitter:url" content="https://yallabalagan.org/">
        <meta property="twitter:title" content="Ялла, Балаган!">
        <meta property="twitter:description" content="Мероприятия связанные с комедией и юмором в Израиле. Подкаст 'Че там у евреев', шоу 'Изотоп Комедия' и многое другое!">
        <meta property="twitter:image" content="https://events-site-yallabalagan.s3.eu-north-1.amazonaws.com/images/yalla_square.jpg">

        <!-- Google Analytics -->
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-RP1612BFV9"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){{dataLayer.push(arguments);}}
          gtag('js', new Date());
          gtag('config', 'G-RP1612BFV9');
        </script>

        <!-- Meta Pixel Code -->
        <script>
        !function(f,b,e,v,n,t,s)
        {{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
        n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
        if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
        n.queue=[];t=b.createElement(e);t.async=!0;
        t.src=v;s=b.getElementsByTagName(e)[0];
        s.parentNode.insertBefore(t,s)}}(window, document,'script',
        'https://connect.facebook.net/en_US/fbevents.js');
        fbq('init', '738718761834602');
        fbq('track', 'PageView');
        </script>
        <noscript><img height="1" width="1" style="display:none"
        src="https://www.facebook.com/tr?id=738718761834602&ev=PageView&noscript=1"
        /></noscript>
        <!-- End Meta Pixel Code -->

        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: #f5f5f5;
                line-height: 1.6;
            }}

            .top-banner {{
                width: 100%;
                height: 250px;
                background: url('https://events-site-yallabalagan.s3.eu-north-1.amazonaws.com/images/top_banner.jpg') center center;
                background-size: cover;
            }}

            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 40px 20px;
                display: grid;
                grid-template-columns: 350px 1fr;
                gap: 40px;
            }}

            .sidebar {{
                background: white;
                padding: 30px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                height: fit-content;
            }}

            /* Sticky scroll only on desktop */
            @media (min-width: 1025px) {{
                .sidebar {{
                    max-height: calc(100vh - 40px);
                    overflow-y: auto;
                    position: sticky;
                    top: 20px;
                }}
            }}

            .sidebar h2 {{
                font-size: 24px;
                margin-bottom: 20px;
                color: #1a202c;
            }}

            .description {{
                color: #4a5568;
                margin-bottom: 20px;
                line-height: 1.8;
            }}

            /* БЛОК ПОДКАСТА */
            .podcast-link-block {{
                background: linear-gradient(135deg, #fef5fb 0%, #fff 100%);
                border: 2px solid #e535ab;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 25px;
            }}

            .podcast-intro {{
                color: #4a5568;
                font-size: 0.95rem;
                margin-bottom: 12px;
                font-weight: 500;
            }}

            .podcast-latest {{
                color: #718096;
                font-size: 0.85rem;
                margin-bottom: 8px;
            }}

            .podcast-link {{
                display: block;
                color: #e535ab;
                text-decoration: none;
                font-weight: 600;
                font-size: 0.95rem;
                line-height: 1.5;
                padding: 12px;
                background: white;
                border-radius: 8px;
                transition: all 0.3s;
                border: 1px solid #fce7f5;
            }}

            .podcast-link:hover {{
                background: #fef5fb;
                transform: translateX(3px);
                border-color: #e535ab;
            }}

            .social-links {{
                display: flex;
                flex-direction: column;
                gap: 12px;
            }}

            .social-link {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 16px;
                background: #f7fafc;
                border-radius: 8px;
                text-decoration: none;
                color: #1a202c;
                transition: all 0.3s ease;
                font-weight: 500;
            }}

            .social-link:hover {{
                background: #e535ab;
                color: white;
                transform: translateX(5px);
            }}

            .social-icon {{
                width: 24px;
                height: 24px;
                font-size: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }}

            {footer_styles}

            .events-section {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}

            .events-section > h1 {{
                font-size: 32px;
                margin-bottom: 40px;
                color: #1a202c;
            }}

            .month-section {{
                margin-bottom: 50px;
            }}

            .month-section:last-child {{
                margin-bottom: 0;
            }}

            .month-header {{
                font-size: 28px;
                font-weight: 700;
                color: #e535ab;
                margin-bottom: 24px;
                padding-bottom: 12px;
                border-bottom: 3px solid #e535ab;
            }}

            .events-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 24px;
            }}

            .event-card-wrapper {{
                display: flex;
                flex-direction: column;
                height: 100%;
            }}

            .event-card {{
                background: white;
                border-radius: 12px;
                border: 2px solid #e2e8f0;
                transition: all 0.3s ease;
                display: flex;
                flex-direction: column;
                overflow: visible;
                height: 100%;
            }}

            .event-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 8px 16px rgba(229, 53, 171, 0.2);
                border-color: #e535ab;
            }}

            .event-link {{
                text-decoration: none;
                color: inherit;
                flex: 1;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                border-radius: 12px 12px 0 0;
            }}

            .event-image {{
                width: 100%;
                height: 200px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                overflow: hidden;
            }}

            .event-image img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}

            .event-info {{
                padding: 20px;
            }}

            .event-date {{
                color: #e535ab;
                font-size: 14px;
                font-weight: 700;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}

            .event-title {{
                font-size: 18px;
                font-weight: 700;
                color: #1a202c;
                line-height: 1.4;
            }}

            /* Calendar Button Styles */
            .calendar-button-container {{
                position: relative;
                padding: 0 20px 20px 20px;
            }}

            .calendar-button-container.active {{
                z-index: 200;
            }}

            .add-to-calendar-btn {{
                width: 100%;
                padding: 10px 14px;
                background: transparent;
                color: #e535ab;
                border: 1.5px solid #e535ab;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                transition: all 0.2s ease;
                font-family: inherit;
            }}

            .add-to-calendar-btn:hover {{
                background: rgba(229, 53, 171, 0.05);
                border-color: #c72d93;
                color: #c72d93;
            }}

            .add-to-calendar-btn:active {{
                transform: scale(0.98);
            }}

            .calendar-icon {{
                font-size: 16px;
            }}

            .dropdown-arrow {{
                font-size: 9px;
                margin-left: auto;
                transition: transform 0.3s ease;
            }}

            .add-to-calendar-btn.active {{
                background: rgba(229, 53, 171, 0.05);
                border-color: #c72d93;
            }}

            .add-to-calendar-btn.active .dropdown-arrow {{
                transform: rotate(180deg);
            }}

            .calendar-dropdown {{
                position: absolute;
                top: calc(100% + 8px);
                left: 0;
                right: 0;
                background: white;
                border-radius: 8px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
                display: none;
                flex-direction: column;
                overflow: hidden;
                z-index: 300;
                border: 1px solid #e2e8f0;
            }}

            .calendar-dropdown.show {{
                display: flex;
            }}

            .calendar-option {{
                padding: 12px 16px;
                text-decoration: none;
                color: #1a202c;
                display: flex;
                align-items: center;
                gap: 10px;
                transition: background 0.2s ease;
                font-size: 14px;
                font-weight: 500;
            }}

            .calendar-option:hover {{
                background: #f7fafc;
            }}

            .calendar-service-icon {{
                font-size: 16px;
                width: 20px;
                text-align: center;
            }}

            .no-events {{
                text-align: center;
                padding: 60px 20px;
                color: #718096;
            }}

            @media (max-width: 1024px) {{
                .container {{
                    grid-template-columns: 1fr;
                    gap: 30px;
                }}
            }}

            @media (max-width: 768px) {{
                .top-banner {{
                    height: 150px;
                }}

                .container {{
                    padding: 20px 15px;
                }}

                .sidebar {{
                    padding: 20px;
                }}

                .podcast-link-block {{
                    padding: 15px;
                }}

                .events-section {{
                    padding: 20px;
                }}

                .events-section > h1 {{
                    font-size: 24px;
                    margin-bottom: 30px;
                }}

                .month-header {{
                    font-size: 22px;
                }}

                .events-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="top-banner"></div>

        <div class="container">
            <aside class="sidebar">
                <h2>О нас</h2>
                <p class="description">
                    Творческое объединение которое делает всякие мероприятия в Израиле, в основном связанные с комедией и юмором. 
                    Мы выпускаем подкаст "Че там у евреев", научно-комедийное шоу "Изотоп Комедия", а так же много другого всякого. 
                    На сайте мероприятия от нас и от людей близких по духу!
                </p>

                {podcast_html}

                <p class="description" style="font-weight: 600; margin-bottom: 20px;">
                    Подпишись на наши соц.сети, чтобы не пропустить контент, приколы и события!
                </p>

                <div class="social-links">
                    <a href="https://instagram.com/yallabala" target="_blank" class="social-link">
                        <span class="social-icon">📷</span>
                        <span>Instagram</span>
                    </a>
                    <a href="https://t.me/yallabala" target="_blank" class="social-link">
                        <span class="social-icon">✈️</span>
                        <span>Telegram</span>
                    </a>
                    <a href="https://youtube.com/@yallabalagan" target="_blank" class="social-link">
                        <span class="social-icon">▶️</span>
                        <span>YouTube</span>
                    </a>
                    <a href="https://facebook.com/YallaBalaganIsrael" target="_blank" class="social-link">
                        <span class="social-icon">👍</span>
                        <span>Facebook</span>
                    </a>
                </div>

                {footer_html}
            </aside>

            <main class="events-section">
                <h1>🎉 Ближайшие события</h1>
                {events_html}
            </main>
        </div>

        <script>
            // Закрытие меню при клике вне его
            document.addEventListener('click', function(event) {{
                if (!event.target.closest('.calendar-button-container')) {{
                    document.querySelectorAll('.calendar-dropdown.show').forEach(dropdown => {{
                        dropdown.classList.remove('show');
                        dropdown.previousElementSibling.classList.remove('active');
                        dropdown.closest('.calendar-button-container').classList.remove('active');
                    }});
                }}
            }});

            function toggleCalendarMenu(event, button) {{
                event.preventDefault();
                event.stopPropagation();

                const container = button.closest('.calendar-button-container');
                const dropdown = container.querySelector('.calendar-dropdown');
                const isActive = dropdown.classList.contains('show');

                // Закрываем все другие открытые меню
                document.querySelectorAll('.calendar-dropdown.show').forEach(d => {{
                    if (d !== dropdown) {{
                        d.classList.remove('show');
                        d.previousElementSibling.classList.remove('active');
                        d.closest('.calendar-button-container').classList.remove('active');
                    }}
                }});

                // Переключаем текущее меню
                dropdown.classList.toggle('show');
                button.classList.toggle('active');
                container.classList.toggle('active');
            }}

            function getEventData(container) {{
                const button = container.querySelector('.add-to-calendar-btn');
                return {{
                    title: button.dataset.eventTitle,
                    date: button.dataset.eventDate,
                    url: button.dataset.eventUrl
                }};
            }}

            function formatDateForCalendar(dateStr) {{
                // Преобразуем дату в формат YYYYMMDD для календарей
                const date = new Date(dateStr);
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${{year}}${{month}}${{day}}`;
            }}

            function addToGoogleCalendar(event, container) {{
                event.preventDefault();
                const data = getEventData(container);
                const dateFormatted = formatDateForCalendar(data.date);

                const params = new URLSearchParams({{
                    action: 'TEMPLATE',
                    text: data.title,
                    dates: `${{dateFormatted}}/${{dateFormatted}}`,
                    details: `Подробнее: ${{data.url}}`,
                    location: 'Израиль'
                }});

                window.open(`https://calendar.google.com/calendar/render?${{params}}`, '_blank');
            }}

            function addToOutlook(event, container) {{
                event.preventDefault();
                const data = getEventData(container);
                const date = new Date(data.date);

                const params = new URLSearchParams({{
                    path: '/calendar/action/compose',
                    rru: 'addevent',
                    subject: data.title,
                    startdt: date.toISOString(),
                    enddt: date.toISOString(),
                    body: `Подробнее: ${{data.url}}`,
                    location: 'Израиль'
                }});

                window.open(`https://outlook.live.com/calendar/0/deeplink/compose?${{params}}`, '_blank');
            }}

            function addToYahoo(event, container) {{
                event.preventDefault();
                const data = getEventData(container);
                const dateFormatted = formatDateForCalendar(data.date);

                const params = new URLSearchParams({{
                    v: 60,
                    title: data.title,
                    st: dateFormatted,
                    et: dateFormatted,
                    desc: `Подробнее: ${{data.url}}`,
                    in_loc: 'Израиль'
                }});

                window.open(`https://calendar.yahoo.com/?${{params}}`, '_blank');
            }}

            function addToAppleCalendar(event, container) {{
                event.preventDefault();
                downloadICS(event, container);
            }}

            function downloadICS(event, container) {{
                event.preventDefault();
                const data = getEventData(container);
                const date = new Date(data.date);

                // Форматируем дату для ICS (YYYYMMDD)
                const dateStr = formatDateForCalendar(data.date);

                const icsContent = [
                    'BEGIN:VCALENDAR',
                    'VERSION:2.0',
                    'PRODID:-//Yallabalagan//Events//RU',
                    'CALSCALE:GREGORIAN',
                    'METHOD:PUBLISH',
                    'BEGIN:VEVENT',
                    `DTSTART;VALUE=DATE:${{dateStr}}`,
                    `DTEND;VALUE=DATE:${{dateStr}}`,
                    `DTSTAMP:${{new Date().toISOString().replace(/[-:]/g, '').split('.')[0]}}Z`,
                    `UID:${{Date.now()}}@yallabalagan.org`,
                    `SUMMARY:${{data.title}}`,
                    `DESCRIPTION:Подробнее: ${{data.url}}`,
                    'LOCATION:Израиль',
                    'STATUS:CONFIRMED',
                    'SEQUENCE:0',
                    'END:VEVENT',
                    'END:VCALENDAR'
                ].join('\\r\\n');

                const blob = new Blob([icsContent], {{ type: 'text/calendar;charset=utf-8' }});
                const link = document.createElement('a');
                link.href = window.URL.createObjectURL(blob);
                link.download = `${{data.title.replace(/[^a-zA-Zа-яА-Я0-9]/g, '_')}}.ics`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }}
        </script>
    </body>
    </html>
    """

    return html


def upload_to_s3(html_content):
    """Загружает HTML на S3"""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key='index.html',
            Body=html_content.encode('utf-8'),
            ContentType='text/html; charset=utf-8',
            CacheControl='max-age=0'
        )
        print(f"HTML uploaded to S3: {S3_BUCKET_NAME}/index.html")
        return True
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return False


def lambda_handler(event, context):
    """
    Главный handler для генерации сайта
    """
    print("Starting site generation...")

    try:
        # 1. Получаем последнее видео из YouTube плейлиста
        youtube_video = None
        if YOUTUBE_API_KEY and YOUTUBE_PLAYLIST_ID:
            print("Получение последнего видео из YouTube плейлиста...")
            youtube_video = get_latest_video_from_playlist(YOUTUBE_API_KEY, YOUTUBE_PLAYLIST_ID)
            if youtube_video:
                print(f"✓ Видео получено: {youtube_video['title']}")
            else:
                print("⚠ Не удалось получить видео из плейлиста")
        else:
            print("⚠ YouTube API не настроен")

        # 2. Получаем события из Notion
        events = get_all_events()

        # 3. Генерируем HTML с информацией о подкасте
        html = generate_html(events, youtube_video)

        # 4. Загружаем в S3
        success = upload_to_s3(html)

        if success:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Site generated successfully',
                    'events_count': len(events),
                    'youtube_video': youtube_video['title'] if youtube_video else None
                })
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps({'message': 'Failed to upload to S3'})
            }

    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'message': f'Error: {str(e)}'})
        }