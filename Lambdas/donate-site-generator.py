import json
import os
import requests
from datetime import datetime
import boto3
import random

NOTION_TOKEN = os.environ['NOTION_TOKEN']
TALENTS_DB_ID = os.environ['TALENTS_DB_ID']
PRODUCTS_DB_ID = os.environ['PRODUCTS_DB_ID']
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

s3_client = boto3.client('s3')

# Contact info
CONTACT_EMAIL = "yalla@yallabalagan.org"
CONTACT_PHONE = "+972506491680"
CONTACT_ADDRESS = "Bat Yam, Rothschild 17"
FUNDRAISING_GOAL = 30000  # ₪30,000

# Projects data
PROJECTS = [
    {
        'name': 'Изотоп Комедия',
        'description': 'Научное шоу Льва Гольдорта, где комики обсуждают новости науки с учёным и пытаются понять, куда катится мир.',
        'photo_url': 'https://donate-yallabalagan.s3.eu-north-1.amazonaws.com/images/projects/5bdf8d33e440e60c518ece0be8dd1498.png'
    },
    {
        'name': 'Еврейский заговор',
        'description': 'Шоу Максима Сотникова, которое признаёт: еврейский заговор существует, и его нужно возглавить.',
        'photo_url': 'https://donate-yallabalagan.s3.eu-north-1.amazonaws.com/images/projects/2025-11-02+21.46.26.jpg'
    },
    {
        'name': 'Шоу Крайней Плотности',
        'description': 'Проект Кирилла Селегея, где три опытных комика слушают и анализируют, как начинаюшие комики рассказывают минуту шуток.',
        'photo_url': 'https://donate-yallabalagan.s3.eu-north-1.amazonaws.com/images/projects/2025-11-02+21.47.13.jpg'
    },
    {
        'name': 'Съемки Стендапа',
        'description': 'Мы постоянно пишем стендап и постоянно выступаем, пришло наконец-то время более ли менее системно его снимать!',
        'photo_url': 'https://donate-yallabalagan.s3.eu-north-1.amazonaws.com/images/projects/58e77288172e45f81075143274df3bc4.png'
    }
]


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def get_text_from_rich_text(rich_text_array):
    """Извлекает текст из Notion rich_text"""
    if not rich_text_array:
        return ""
    return "".join([t.get('plain_text', '') for t in rich_text_array])


def get_active_talents():
    """Получает все активные таланты из Notion"""
    response = requests.post(
        f"{NOTION_API_URL}/databases/{TALENTS_DB_ID}/query",
        headers=notion_headers(),
        json={
            "filter": {
                "property": "Status",
                "select": {
                    "equals": "Active"
                }
            },
            "sorts": [
                {
                    "property": "Order",
                    "direction": "ascending"
                }
            ]
        }
    )

    if response.status_code != 200:
        print(f"Error fetching talents: {response.text}")
        return []

    pages = response.json().get('results', [])
    talents = []

    for page in pages:
        props = page['properties']

        talent = {
            'id': page['id'],
            'name': get_text_from_rich_text(props.get('Name', {}).get('title', [])),
            'slug': get_text_from_rich_text(props.get('Slug', {}).get('rich_text', [])),
            'photo_url': props.get('Photo_URL', {}).get('url', ''),
            'bio': get_text_from_rich_text(props.get('Bio', {}).get('rich_text', [])),
            'role': get_text_from_rich_text(props.get('Role', {}).get('rich_text', [])),
            'instagram': props.get('Instagram', {}).get('url', ''),
            'telegram': props.get('Telegram', {}).get('url', ''),
            'youtube': props.get('YouTube', {}).get('url', ''),
            'facebook': props.get('Facebook', {}).get('url', ''),
            'featured_video': props.get('Featured_Video', {}).get('url', ''),
            'products_count': props.get('Products_Count', {}).get('rollup', {}).get('number', 0),
            'total_sold': props.get('Total_Sold', {}).get('rollup', {}).get('number', 0)
        }

        talents.append(talent)

    print(f"Found {len(talents)} active talents")
    return talents


def get_active_products():
    """Получает все активные товары из Notion"""
    response = requests.post(
        f"{NOTION_API_URL}/databases/{PRODUCTS_DB_ID}/query",
        headers=notion_headers(),
        json={
            "filter": {
                "property": "Status",
                "select": {
                    "equals": "Active"
                }
            },
            "sorts": [
                {
                    "property": "Order",
                    "direction": "ascending"
                }
            ]
        }
    )

    if response.status_code != 200:
        print(f"Error fetching products: {response.text}")
        return []

    pages = response.json().get('results', [])
    products = []

    for page in pages:
        props = page['properties']

        # Получаем все ID талантов из Relation
        talent_relation = props.get('Talent', {}).get('relation', [])
        talent_ids = [rel['id'] for rel in talent_relation] if talent_relation else []

        product = {
            'id': page['id'],
            'name': get_text_from_rich_text(props.get('Name', {}).get('title', [])),
            'slug': get_text_from_rich_text(props.get('Slug', {}).get('rich_text', [])),
            'talent_ids': talent_ids,
            'type': props.get('Type', {}).get('select', {}).get('name', 'Individual'),
            'short_description': get_text_from_rich_text(props.get('Short_Description', {}).get('rich_text', [])),
            'full_description': get_text_from_rich_text(props.get('Full_Description', {}).get('rich_text', [])),
            'what_you_get': get_text_from_rich_text(props.get('What_You_Get', {}).get('rich_text', [])),
            'price_ils': props.get('Price_ILS', {}).get('number', 0),
            'price_stars': props.get('Price_Stars', {}).get('number', 0),
            'total_slots': props.get('Total_Slots', {}).get('number', 0),
            'sold_slots': props.get('Sold_Slots', {}).get('number', 0),
            'group_size': props.get('Group_Size', {}).get('number'),
            'photo_url': props.get('Photo_URL', {}).get('url', ''),
            'gallery_urls': get_text_from_rich_text(props.get('Gallery_URLs', {}).get('rich_text', [])),
            'tg_post_link': props.get('Tg_Post_link', {}).get('url', ''),
            'tg_code': get_text_from_rich_text(props.get('Tg_Code', {}).get('rich_text', []))
        }

        products.append(product)

    print(f"Found {len(products)} active products")
    return products


def calculate_total_raised(products):
    """Считает общую сумму собранных денег"""
    total = sum(p['sold_slots'] * p['price_ils'] for p in products)
    return total


def generate_progress_bar(total_raised, goal):
    """Генерирует HTML прогресс-бара"""
    percentage = min(int((total_raised / goal) * 100), 100)

    return f"""
    <div class="fundraising-progress">
        <h2 class="progress-title">🎬 Поддержи съемки нового сезона!</h2>
        <div class="progress-stats">
            <span class="raised">Собрано: ₪{total_raised:,}</span>
            <span class="goal">из ₪{goal:,}</span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {percentage}%"></div>
        </div>
        <div class="progress-percentage">{percentage}%</div>
    </div>
    """


def generate_footer_html():
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
            <a href="https://yallabalagan.org/privacy" target="_blank">Privacy Policy</a>
            <span class="separator">•</span>
            <a href="https://yallabalagan.org/terms" target="_blank">Terms & Conditions</a>
        </div>
    </div>
    """


def generate_index_page(talents, products, total_raised):
    """Генерирует главную страницу"""

    progress_bar_html = generate_progress_bar(total_raised, FUNDRAISING_GOAL)

    # Генерируем карточки проектов
    projects_html = '<div class="projects-grid">'

    for project in PROJECTS:
        projects_html += f"""
        <div class="project-card">
            <div class="project-photo">
                <img src="{project['photo_url']}" alt="{project['name']}">
            </div>
            <div class="project-info">
                <h3>{project['name']}</h3>
                <p class="project-description">{project['description']}</p>
            </div>
        </div>
        """

    projects_html += '</div>'

    # Генерируем карточки талантов
    talents_html = '<div class="talents-grid">'

    for talent in talents:
        talents_html += f"""
        <div class="talent-card">
            <a href="/talent/{talent['slug']}/" class="talent-link">
                <div class="talent-photo">
                    <img src="{talent['photo_url']}" alt="{talent['name']}">
                </div>
                <div class="talent-info">
                    <h3>{talent['name']}</h3>
                    <p class="talent-role">{talent['role']}</p>
                </div>
            </a>
        </div>
        """

    talents_html += '</div>'

    footer_html = generate_footer_html()

    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Поддержи Ялла, Балаган! - Фандрайзинг</title>
        <link rel="icon" type="image/png" href="/favicon.png">
        <link rel="apple-touch-icon" href="/favicon.png">
        <meta property="og:title" content="Поддержи Ялла, Балаган!">
        <meta property="og:description" content="Собираем средства на съемки нового сезона. Поддержи комиков и получи крутые награды!">
        <meta property="og:image" content="https://donate-yallabalagan.s3.eu-north-1.amazonaws.com/images/og-image.jpg">
        <meta property="og:url" content="https://donate.yallabalagan.org">

        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
                line-height: 1.6;
                color: #1a202c;
            }}

            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 40px 20px;
            }}

            /* Параллельный лейаут для прогресса и описания */
            .hero-section {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 30px;
                margin-bottom: 40px;
            }}

            .fundraising-progress {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}

            .progress-title {{
                font-size: 28px;
                margin-bottom: 20px;
                color: #1a202c;
                text-align: center;
            }}

            .progress-stats {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 15px;
                font-size: 18px;
                font-weight: 600;
            }}

            .raised {{
                color: #e535ab;
            }}

            .goal {{
                color: #718096;
            }}

            .progress-bar {{
                width: 100%;
                height: 30px;
                background: #e2e8f0;
                border-radius: 15px;
                overflow: hidden;
                margin-bottom: 10px;
            }}

            .progress-fill {{
                height: 100%;
                background: linear-gradient(90deg, #e535ab 0%, #c72d93 100%);
                transition: width 0.3s ease;
            }}

            .progress-percentage {{
                text-align: right;
                font-size: 24px;
                font-weight: 700;
                color: #e535ab;
            }}

            .campaign-description {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}

            .campaign-description h2 {{
                font-size: 24px;
                margin-bottom: 15px;
                color: #e535ab;
            }}

            .campaign-description p {{
                color: #4a5568;
                line-height: 1.8;
                margin-bottom: 15px;
            }}

            /* Секция проектов */
            .projects-section {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                margin-bottom: 40px;
            }}

            .projects-section h2 {{
                font-size: 32px;
                margin-bottom: 30px;
                color: #1a202c;
            }}

            .projects-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 24px;
            }}

            .project-card {{
                background: white;
                border-radius: 12px;
                overflow: hidden;
                transition: all 0.3s ease;
                aspect-ratio: 16/9;
                position: relative;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}

            .project-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 12px 24px rgba(229, 53, 171, 0.3);
            }}

            .project-photo {{
                width: 100%;
                height: 100%;
                overflow: hidden;
                position: absolute;
                top: 0;
                left: 0;
            }}

            .project-photo img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}

            .project-info {{
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                padding: 20px;
                background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.75) 80%, transparent 100%);
                color: white;
            }}

            .project-info h3 {{
                font-size: 16px;
                margin-bottom: 8px;
                color: white;
                font-weight: 700;
            }}

            .project-description {{
                color: rgba(255,255,255,0.9);
                font-size: 11px;
                line-height: 1.4;
                overflow: hidden;
                display: -webkit-box;
                -webkit-line-clamp: 4;
                -webkit-box-orient: vertical;
                text-overflow: ellipsis;
            }}

            /* Секция талантов */
            .talents-section {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}

            .talents-section h2 {{
                font-size: 32px;
                margin-bottom: 30px;
                color: #1a202c;
            }}

            .talents-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 24px;
            }}

            .talent-card {{
                background: white;
                border-radius: 12px;
                overflow: hidden;
                transition: all 0.3s ease;
                aspect-ratio: 4/5;
                position: relative;
            }}

            .talent-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 12px 24px rgba(229, 53, 171, 0.3);
            }}

            .talent-link {{
                text-decoration: none;
                color: inherit;
                display: block;
                height: 100%;
                position: relative;
            }}

            .talent-photo {{
                width: 100%;
                height: 100%;
                overflow: hidden;
                position: absolute;
                top: 0;
                left: 0;
            }}

            .talent-photo img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}

            .talent-info {{
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                padding: 20px;
                background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.75) 80%, transparent 100%);
                color: white;
                min-height: 90px;
            }}

            .talent-info h3 {{
                font-size: 20px;
                margin-bottom: 5px;
                color: white;
                font-weight: 700;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}

            .talent-role {{
                color: rgba(255,255,255,0.9);
                font-size: 14px;
                margin-bottom: 0;
                line-height: 1.4;
                overflow: hidden;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                text-overflow: ellipsis;
            }}

            .site-footer {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                margin-top: 40px;
            }}

            .footer-contacts h3 {{
                font-size: 18px;
                margin-bottom: 15px;
                color: #1a202c;
            }}

            .contact-item {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                margin: 0 15px 10px 15px;
                color: #4a5568;
                font-size: 14px;
            }}

            .contact-item a {{
                color: #4a5568;
                text-decoration: none;
                transition: color 0.2s;
            }}

            .contact-item a:hover {{
                color: #e535ab;
            }}

            .footer-links {{
                margin-top: 20px;
                font-size: 13px;
            }}

            .footer-links a {{
                color: #718096;
                text-decoration: none;
                margin: 0 10px;
            }}

            .footer-links a:hover {{
                color: #e535ab;
            }}

            .separator {{
                color: #cbd5e0;
            }}

            @media (min-width: 1200px) {{
                .projects-grid {{
                    grid-template-columns: repeat(3, 1fr);
                }}
            }}

            @media (max-width: 768px) {{
                .container {{
                    padding: 20px 15px;
                }}

                .hero-section {{
                    grid-template-columns: 1fr;
                    gap: 20px;
                }}

                .fundraising-progress {{
                    padding: 25px 20px;
                }}

                .campaign-description {{
                    padding: 25px 20px;
                }}

                .progress-title {{
                    font-size: 22px;
                }}

                .projects-grid {{
                    grid-template-columns: 1fr;
                }}

                .talents-grid {{
                    grid-template-columns: 1fr;
                }}

                .contact-item {{
                    display: flex;
                    margin: 10px 0;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="hero-section">
                {progress_bar_html}

                <div class="campaign-description">
                    <h2>О кампании</h2>
                    <p>
                        Мы — Ялла, Балаган, творческое объединение израильтян. В основном мы занимаемся комедией — 
                        делаем стендап-шоу и выпускаем контент на YouTube. Здесь мы собираем средства на новый сезон съёмок. 
                        Помоги нам — круто будет!
                    </p>
                    <p>
                        Мы решили, что просто делать донаты — это уныло, поэтому каждый талант в нашей орбите предлагает «товары» — 
                        что-то, что он готов сделать для вас за ваш донат. Плейлист от Кирилла Селегея, футболка от Вовы Тамаркина, 
                        экскурсия от Льва Гольдорта и многое другое. Поддержите нас и получите что-то крутое и уникальное!
                    </p>
                    <p>
                        Ниже вы можете ознакомиться с проектами, на которые мы собираем средства, и с талантами, которые предлагают всякие штуки!
                    </p>

                </div>
            </div>

            <div class="projects-section">
                <h2>🎯 Шоу, которые хотим сделать в будущем году (на них нельзя кликать)</h2>
                {projects_html}
            </div>

            <div class="talents-section">
                <h2>🎭 Наши таланты (кликайте на них, там приколы!)</h2>
                {talents_html}
            </div>
            <footer class="site-footer">
            {footer_html}
            </footer>
        </div>
    </body>
    </html>
    """

    return html


def upload_to_s3(key, content, content_type='text/html'):
    """Загружает файл в S3"""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=content.encode('utf-8') if isinstance(content, str) else content,
            ContentType=f'{content_type}; charset=utf-8',
            CacheControl='max-age=0'
        )
        print(f"Uploaded to S3: {key}")
        return True
    except Exception as e:
        print(f"Error uploading {key}: {e}")
        return False


def extract_youtube_id(url):
    """Извлекает video ID из YouTube URL"""
    if not url:
        return None

    import re
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{{11}})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def simple_markdown(text):
    """Простая конвертация markdown в HTML"""
    if not text:
        return ""

    # Заменяем переносы строк
    text = text.replace('\n\n', '</p><p>')
    text = text.replace('\n', '<br>')

    # Оборачиваем в параграфы
    if text and not text.startswith('<p>'):
        text = '<p>' + text + '</p>'

    return text


def generate_talent_page(talent, all_products, all_talents):
    """Генерирует страницу таланта с новым лейаутом"""

    # Фильтруем товары этого таланта
    talent_products = [p for p in all_products if talent['id'] in p['talent_ids']]

    print(f"=== Talent: {talent['name']} ===")
    print(f"Talent ID: {talent['id']}")
    print(f"Products for this talent: {len(talent_products)}")

    # Генерируем карточки товаров
    products_html = '<div class="products-grid">'

    for product in talent_products:
        available_slots = product['total_slots'] - product['sold_slots']
        percentage = int((product['sold_slots'] / product['total_slots']) * 100) if product['total_slots'] > 0 else 0

        products_html += f"""
        <div class="product-card">
            <a href="/product/{product['slug']}/" class="product-link">
                <div class="product-photo">
                    <img src="{product['photo_url']}" alt="{product['name']}">
                </div>
                <div class="product-info">
                    <h3>{product['name']}</h3>
                    <p class="product-description">{product['short_description']}</p>
                    <p class="product-price">₪{product['price_ils']}</p>
                    <div class="product-progress">
                        <div class="progress-bar-small">
                            <div class="progress-fill-small" style="width: {percentage}%"></div>
                        </div>
                        <p class="slots-info">Осталось: {available_slots} из {product['total_slots']}</p>
                    </div>
                </div>
            </a>
        </div>
        """

    products_html += '</div>'

    if not talent_products:
        products_html = '<p class="no-products">Пока нет доступных товаров</p>'

    # Соцсети
    socials_html = '<div class="talent-socials">'
    if talent['instagram']:
        socials_html += f'<a href="{talent["instagram"]}" target="_blank" class="social-btn">📷 Instagram</a>'
    if talent['telegram']:
        socials_html += f'<a href="{talent["telegram"]}" target="_blank" class="social-btn">✈️ Telegram</a>'
    if talent['youtube']:
        socials_html += f'<a href="{talent["youtube"]}" target="_blank" class="social-btn">▶️ YouTube</a>'
    if talent['facebook']:
        socials_html += f'<a href="{talent["facebook"]}" target="_blank" class="social-btn">👍 Facebook</a>'
    socials_html += '</div>'

    # Видео
    video_html = ""
    if talent['featured_video']:
        video_id = extract_youtube_id(talent['featured_video'])
        if video_id:
            video_html = f"""
            <div class="sidebar-video">
                <h3>Видео</h3>
                <div class="video-container">
                    <iframe 
                        src="https://www.youtube.com/embed/{video_id}" 
                        frameborder="0" 
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                        allowfullscreen>
                    </iframe>
                </div>
            </div>
            """

    # Биография
    bio_html = simple_markdown(talent['bio'])

    # Генерируем галерею из 4 случайных талантов (кроме текущего)
    other_talents = [t for t in all_talents if t['id'] != talent['id']]
    random_talents = random.sample(other_talents, min(4, len(other_talents)))

    talents_gallery_html = ""
    if random_talents:
        talents_gallery_html = '<div class="talents-gallery"><h3>Другие таланты</h3><div class="talents-grid">'
        for t in random_talents:
            talents_gallery_html += f"""
            <a href="/talent/{t['slug']}/" class="talent-mini-card">
                <div class="talent-mini-photo">
                    <img src="{t['photo_url']}" alt="{t['name']}">
                </div>
                <div class="talent-mini-info">
                    <div class="talent-mini-name">{t['name']}</div>
                    <div class="talent-mini-role">{t['role']}</div>
                </div>
            </a>
            """
        talents_gallery_html += '</div></div>'

    footer_html = generate_footer_html()

    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{talent['name']} - Поддержи Ялла, Балаган!</title>
        <link rel="icon" type="image/png" href="/favicon.png">
        <link rel="apple-touch-icon" href="/favicon.png">
        <meta property="og:title" content="{talent['name']} - Поддержи Ялла, Балаган!">
        <meta property="og:description" content="{talent['role']}">
        <meta property="og:image" content="{talent['photo_url']}">
        <meta property="og:url" content="https://donate.yallabalagan.org/talent/{talent['slug']}/">

        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
                line-height: 1.6;
                color: #1a202c;
            }}

            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 40px 20px;
            }}

            .breadcrumbs {{
                margin-bottom: 20px;
                color: #718096;
                font-size: 14px;
            }}

            .breadcrumbs a {{
                color: #e535ab;
                text-decoration: none;
            }}

            .breadcrumbs a:hover {{
                text-decoration: underline;
            }}

            .back-button {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 20px;
                padding: 10px 20px;
                background: white;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                color: #1a202c;
                text-decoration: none;
                font-weight: 500;
                transition: all 0.2s;
            }}

            .back-button:hover {{
                border-color: #e535ab;
                color: #e535ab;
            }}

            .page-layout {{
                display: grid;
                grid-template-columns: 350px 1fr;
                gap: 40px;
            }}

            .sidebar {{
                background: white;
                padding: 30px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                position: sticky;
                top: 20px;
                max-height: calc(100vh - 40px);
                overflow-y: auto;
            }}

            .sidebar-photo {{
                width: 100%;
                aspect-ratio: 4/5;
                border-radius: 12px;
                overflow: hidden;
                margin-bottom: 20px;
            }}

            .sidebar-photo img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}

            .sidebar h1 {{
                font-size: 28px;
                margin-bottom: 10px;
                color: #1a202c;
            }}

            .role {{
                color: #718096;
                margin-bottom: 20px;
                font-size: 16px;
            }}

            .talent-socials {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-bottom: 25px;
                padding-bottom: 25px;
                border-bottom: 2px solid #e2e8f0;
            }}

            .social-btn {{
                display: inline-flex;
                align-items: center;
                gap: 5px;
                padding: 8px 16px;
                background: #f7fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                color: #1a202c;
                text-decoration: none;
                font-size: 14px;
                transition: all 0.2s;
            }}

            .social-btn:hover {{
                background: #e535ab;
                color: white;
                border-color: #e535ab;
            }}

            .sidebar-bio {{
                margin-bottom: 25px;
            }}

            .sidebar-bio h3 {{
                font-size: 18px;
                margin-bottom: 10px;
                color: #1a202c;
            }}

            .sidebar-bio p {{
                color: #4a5568;
                line-height: 1.6;
            }}

            .sidebar-video {{
                margin-top: 25px;
                padding-top: 25px;
                border-top: 2px solid #e2e8f0;
            }}

            .sidebar-video h3 {{
                font-size: 18px;
                margin-bottom: 15px;
                color: #1a202c;
            }}

            .video-container {{
                position: relative;
                padding-bottom: 56.25%;
                height: 0;
                overflow: hidden;
                border-radius: 8px;
            }}

            .video-container iframe {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
            }}

            .products-section {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}

            .products-section h2 {{
                font-size: 32px;
                margin-bottom: 30px;
                color: #1a202c;
            }}

            .products-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 24px;
            }}

            .product-card {{
                background: white;
                border-radius: 12px;
                overflow: hidden;
                transition: all 0.3s ease;
                aspect-ratio: 4/5;
                position: relative;
            }}

            .product-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 12px 24px rgba(229, 53, 171, 0.3);
            }}

            .product-link {{
                text-decoration: none;
                color: inherit;
                display: block;
                height: 100%;
                position: relative;
            }}

            .product-photo {{
                width: 100%;
                height: 100%;
                overflow: hidden;
                position: absolute;
                top: 0;
                left: 0;
            }}

            .product-photo img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}

            .product-info {{
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                padding: 20px;
                background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.8) 70%, transparent 100%);
                color: white;
            }}

            .product-info h3 {{
                font-size: 18px;
                margin-bottom: 8px;
                color: white;
                font-weight: 700;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}

            .product-description {{
                color: rgba(255,255,255,0.85);
                font-size: 13px;
                line-height: 1.3;
                margin-bottom: 10px;
                overflow: hidden;
                display: -webkit-box;
                -webkit-line-clamp: 4;
                -webkit-box-orient: vertical;
                text-overflow: ellipsis;
            }}

            .product-price {{
                color: #ffd700;
                font-size: 16px;
                font-weight: 600;
                margin-bottom: 10px;
            }}

            .product-progress {{
                margin-top: 8px;
            }}

            .progress-bar-small {{
                width: 100%;
                height: 8px;
                background: rgba(255,255,255,0.3);
                border-radius: 4px;
                overflow: hidden;
                margin-bottom: 5px;
            }}

            .progress-fill-small {{
                height: 100%;
                background: #e535ab;
                transition: width 0.3s ease;
            }}

            .slots-info {{
                font-size: 12px;
                color: rgba(255,255,255,0.8);
                margin: 0;
            }}

            .no-products {{
                text-align: center;
                color: #718096;
                padding: 40px;
            }}

            .site-footer {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                margin-top: 40px;
            }}

            .footer-contacts h3 {{
                font-size: 18px;
                margin-bottom: 15px;
                color: #1a202c;
            }}

            .contact-item {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                margin: 0 15px 10px 15px;
                color: #4a5568;
                font-size: 14px;
            }}

            .contact-item a {{
                color: #4a5568;
                text-decoration: none;
                transition: color 0.2s;
            }}

            .contact-item a:hover {{
                color: #e535ab;
            }}

            .footer-links {{
                margin-top: 20px;
                font-size: 13px;
            }}

            .footer-links a {{
                color: #718096;
                text-decoration: none;
                margin: 0 10px;
            }}

            .footer-links a:hover {{
                color: #e535ab;
            }}

            .separator {{
                color: #cbd5e0;
            }}

            @media (max-width: 1024px) {{
                .page-layout {{
                    grid-template-columns: 1fr;
                    gap: 30px;
                }}

                .sidebar {{
                    position: static;
                    max-height: none;
                }}
            }}

            @media (max-width: 768px) {{
                .container {{
                    padding: 20px 15px;
                }}

                .sidebar {{
                    padding: 20px;
                }}

                .sidebar h1 {{
                    font-size: 24px;
                }}

                .products-section {{
                    padding: 25px;
                }}

                .products-grid {{
                    grid-template-columns: 1fr;
                }}

                .contact-item {{
                    display: flex;
                    margin: 10px 0;
                }}
            }}

            /* Галерея талантов */
            .talents-gallery {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                margin-top: 40px;
            }}

            .talents-gallery h3 {{
                font-size: 24px;
                margin-bottom: 25px;
                color: #1a202c;
                text-align: center;
            }}

            .talents-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
            }}

            .talent-mini-card {{
                text-decoration: none;
                color: inherit;
                display: block;
                border-radius: 12px;
                overflow: hidden;
                transition: all 0.3s ease;
                background: white;
                border: 1px solid #e2e8f0;
            }}

            .talent-mini-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 8px 16px rgba(229, 53, 171, 0.2);
                border-color: #e535ab;
            }}

            .talent-mini-photo {{
                width: 100%;
                aspect-ratio: 4/5;
                overflow: hidden;
            }}

            .talent-mini-photo img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}

            .talent-mini-info {{
                padding: 15px;
                text-align: center;
            }}

            .talent-mini-name {{
                font-size: 16px;
                font-weight: 600;
                color: #1a202c;
                margin-bottom: 5px;
            }}

            .talent-mini-role {{
                font-size: 13px;
                color: #718096;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="breadcrumbs">
                <a href="/">Главная</a> → {talent['name']}
            </div>

            <a href="/" class="back-button">
                ← Назад к талантам
            </a>

            <div class="page-layout">
                <aside class="sidebar">
                    <div class="sidebar-photo">
                        <img src="{talent['photo_url']}" alt="{talent['name']}">
                    </div>

                    <h1>{talent['name']}</h1>
                    <p class="role">{talent['role']}</p>

                    {socials_html}

                    <div class="sidebar-bio">
                        <h3>О {talent['name']}</h3>
                        {bio_html}
                    </div>

                    {video_html}
                </aside>

                <main class="products-section">
                    <h2>{talent['name']} предлагает вот такие товары:</h2>
                    {products_html}
                </main>
            </div>

            {talents_gallery_html}

            <footer class="site-footer">
                    {footer_html}
            </footer>
        </div>
    </body>
    </html>
    """

    return html


def generate_product_page(product, talent, all_products, all_talents):
    """Генерирует страницу товара"""

    # Прогресс продаж
    available_slots = product['total_slots'] - product['sold_slots']
    percentage = int((product['sold_slots'] / product['total_slots']) * 100) if product['total_slots'] > 0 else 0

    # Галерея (если есть)
    gallery_html = ""
    if product.get('gallery_urls'):
        urls = [url.strip() for url in product['gallery_urls'].split(',') if url.strip()]
        if urls:
            gallery_html = '<div class="gallery">'
            for url in urls:
                gallery_html += f'<img src="{url}" alt="Gallery image">'
            gallery_html += '</div>'

    # Форматируем описание и "Что вы получите"
    full_desc_html = simple_markdown(product['full_description'])
    what_you_get_html = simple_markdown(product['what_you_get'])

    # Типы товара
    type_name = get_type_name(product['type'])

    # Информация о группе
    group_info_html = ""
    current_group_html = ""

    if product['type'] == 'Group' and product.get('group_size'):
        group_info_html = f"""
        <div class="info-item">
            <span class="info-label">Размер группы:</span>
            <span class="info-value">{product['group_size']} {get_word_form(product['group_size'], 'человек', 'человека', 'человек')}</span>
        </div>
        """

        # Расчёт заполненности текущей группы
        current_in_group = product['sold_slots'] % product['group_size']
        if current_in_group > 0:  # Есть незавершённая группа
            spots_left_in_group = product['group_size'] - current_in_group
            current_group_html = f"""
            <div class="current-group-status">
                🔥 В текущей группе: {current_in_group}/{product['group_size']} {get_word_form(current_in_group, 'человек', 'человека', 'человек')}
                <br>
                <strong>Осталось {spots_left_in_group} {get_word_form(spots_left_in_group, 'место', 'места', 'мест')} до старта!</strong>
            </div>
            """

    # Генерируем галерею из 5 случайных продуктов от других талантов
    other_products = [p for p in all_products if not any(tid in product['talent_ids'] for tid in p['talent_ids'])]
    random_products = random.sample(other_products, min(5, len(other_products)))

    products_gallery_html = ""
    if random_products:
        products_gallery_html = '<div class="products-gallery"><h3>Другие продукты</h3><div class="products-gallery-grid">'
        for p in random_products:
            p_talent = next((t for t in all_talents if t['id'] == p['talent_ids'][0]), None) if p[
                'talent_ids'] else None
            if p_talent:
                p_available = p['total_slots'] - p['sold_slots']
                p_percentage = int((p['sold_slots'] / p['total_slots']) * 100) if p['total_slots'] > 0 else 0

                products_gallery_html += f"""
                <a href="/product/{p['slug']}/" class="product-gallery-card">
                    <div class="product-gallery-photo">
                        <img src="{p['photo_url']}" alt="{p['name']}">
                    </div>
                    <div class="product-gallery-info">
                        <div class="product-gallery-talent">{p_talent['name']}</div>
                        <div class="product-gallery-name">{p['name']}</div>
                        <div class="product-gallery-price">₪{p['price_ils']}</div>
                        <div class="product-gallery-progress">
                            <div class="progress-bar-small">
                                <div class="progress-fill-small" style="width: {p_percentage}%"></div>
                            </div>
                            <div class="slots-info-small">{p_available}/{p['total_slots']}</div>
                        </div>
                    </div>
                </a>
                """
        products_gallery_html += '</div></div>'

    footer_html = generate_footer_html()

    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{product['name']} - {talent['name']}</title>
        <link rel="icon" type="image/png" href="/favicon.png">
        <link rel="apple-touch-icon" href="/favicon.png">
        <meta property="og:title" content="{product['name']} - {talent['name']}">
        <meta property="og:description" content="{product['short_description']}">
        <meta property="og:image" content="{product['photo_url']}">
        <meta property="og:url" content="https://donate.yallabalagan.org/product/{product['slug']}/">

        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
                line-height: 1.6;
                color: #1a202c;
            }}

            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 40px 20px;
            }}

            .breadcrumbs {{
                margin-bottom: 20px;
                color: #718096;
                font-size: 14px;
            }}

            .breadcrumbs a {{
                color: #e535ab;
                text-decoration: none;
            }}

            .breadcrumbs a:hover {{
                text-decoration: underline;
            }}

            .back-button {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 20px;
                padding: 10px 20px;
                background: white;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                color: #1a202c;
                text-decoration: none;
                font-weight: 500;
                transition: all 0.2s;
            }}

            .back-button:hover {{
                border-color: #e535ab;
                color: #e535ab;
            }}

            .product-layout {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 40px;
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}

            .product-image {{
                width: 100%;
                aspect-ratio: 4/5;
                border-radius: 12px;
                overflow: hidden;
            }}

            .product-image img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}

            .gallery {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
                gap: 10px;
                margin-top: 15px;
            }}

            .gallery img {{
                width: 100%;
                aspect-ratio: 1;
                object-fit: cover;
                border-radius: 8px;
                cursor: pointer;
                transition: transform 0.2s;
            }}

            .gallery img:hover {{
                transform: scale(1.05);
            }}

            .product-details h1 {{
                font-size: 32px;
                margin-bottom: 10px;
                color: #1a202c;
            }}

            .product-type {{
                display: inline-block;
                padding: 6px 12px;
                background: #e535ab;
                color: white;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 20px;
            }}

            .product-price {{
                font-size: 36px;
                font-weight: 700;
                color: #e535ab;
                margin-bottom: 20px;
            }}

            .product-info {{
                margin-bottom: 30px;
                padding-bottom: 25px;
                border-bottom: 2px solid #e2e8f0;
            }}

            .info-item {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 15px;
                font-size: 16px;
            }}

            .info-label {{
                color: #718096;
            }}

            .info-value {{
                font-weight: 600;
                color: #1a202c;
            }}

            .progress-section {{
                background: #f7fafc;
                padding: 20px;
                border-radius: 12px;
                margin-bottom: 30px;
            }}

            .progress-text {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 10px;
                font-size: 14px;
                color: #718096;
            }}

            .progress-bar {{
                width: 100%;
                height: 12px;
                background: #e2e8f0;
                border-radius: 6px;
                overflow: hidden;
                margin-bottom: 10px;
            }}

            .progress-fill {{
                height: 100%;
                background: linear-gradient(90deg, #e535ab 0%, #c72d93 100%);
                transition: width 0.3s ease;
            }}

            .availability {{
                font-size: 18px;
                font-weight: 600;
                color: #1a202c;
            }}

            .availability.limited {{
                color: #e535ab;
            }}

            .description-section {{
                margin-bottom: 30px;
            }}

            .description-section h3 {{
                font-size: 20px;
                margin-bottom: 15px;
                color: #1a202c;
            }}

            .description-section p {{
                color: #4a5568;
                line-height: 1.8;
            }}

            .purchase-button {{
                width: 100%;
                padding: 18px;
                background: linear-gradient(135deg, #e535ab 0%, #c72d93 100%);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 18px;
                font-weight: 700;
                cursor: pointer;
                transition: all 0.3s ease;
                font-family: inherit;
            }}

            .purchase-button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(229, 53, 171, 0.4);
            }}

            .purchase-button:disabled {{
                background: #cbd5e0;
                cursor: not-allowed;
                transform: none;
            }}

            .payment-buttons {{
                display: flex;
                flex-direction: column;
                gap: 15px;
            }}

            .telegram-button {{
                width: 100%;
                padding: 18px;
                background: linear-gradient(135deg, #0088cc 0%, #006ba3 100%);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 18px;
                font-weight: 700;
                cursor: pointer;
                transition: all 0.3s ease;
                font-family: inherit;
            }}

            .telegram-button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(0, 136, 204, 0.4);
            }}

            .telegram-button:disabled {{
                background: #cbd5e0;
                cursor: not-allowed;
                transform: none;
            }}

            .payment-divider {{
                display: flex;
                align-items: center;
                text-align: center;
                margin: 10px 0;
                color: #718096;
                font-size: 14px;
            }}

            .payment-divider::before,
            .payment-divider::after {{
                content: '';
                flex: 1;
                border-bottom: 1px solid #e2e8f0;
            }}

            .payment-divider span {{
                padding: 0 15px;
            }}

            .tg-link {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                margin-top: 15px;
                padding: 12px 24px;
                background: #0088cc;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                transition: background 0.2s;
            }}

            .tg-link:hover {{
                background: #006ba3;
            }}

            .site-footer {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                margin-top: 40px;
            }}

            .footer-contacts h3 {{
                font-size: 18px;
                margin-bottom: 15px;
                color: #1a202c;
            }}

            .contact-item {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                margin: 0 15px 10px 15px;
                color: #4a5568;
                font-size: 14px;
            }}

            .contact-item a {{
                color: #4a5568;
                text-decoration: none;
                transition: color 0.2s;
            }}

            .contact-item a:hover {{
                color: #e535ab;
            }}

            .footer-links {{
                margin-top: 20px;
                font-size: 13px;
            }}

            .footer-links a {{
                color: #718096;
                text-decoration: none;
                margin: 0 10px;
            }}

            .footer-links a:hover {{
                color: #e535ab;
            }}

            .separator {{
                color: #cbd5e0;
            }}

            /* Модалка */
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
            }}

            .modal-content {{
                background: white;
                margin: 5% auto;
                padding: 40px;
                border-radius: 16px;
                max-width: 500px;
                position: relative;
                max-height: 85vh;
                overflow-y: auto;
            }}

            .close {{
                position: absolute;
                right: 20px;
                top: 20px;
                font-size: 28px;
                font-weight: bold;
                color: #718096;
                cursor: pointer;
                line-height: 1;
            }}

            .close:hover {{
                color: #e535ab;
            }}

            .modal-content h2 {{
                margin-bottom: 25px;
                color: #1a202c;
            }}

            .form-group {{
                margin-bottom: 20px;
            }}

            .form-group label {{
                display: block;
                margin-bottom: 8px;
                color: #1a202c;
                font-weight: 600;
            }}

            .form-group input,
            .form-group textarea {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 16px;
                font-family: inherit;
                transition: border-color 0.2s;
            }}

            .form-group input:focus,
            .form-group textarea:focus {{
                outline: none;
                border-color: #e535ab;
            }}

            .form-group small {{
                display: block;
                margin-top: 5px;
                color: #718096;
                font-size: 13px;
            }}

            .submit-button {{
                width: 100%;
                padding: 15px;
                background: #e535ab;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.2s;
                font-family: inherit;
            }}

            .submit-button:hover {{
                background: #c72d93;
            }}

            .submit-button:disabled {{
                background: #cbd5e0;
                cursor: not-allowed;
            }}

            .form-message {{
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                display: none;
            }}

            .form-message.success {{
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
                display: block;
            }}

            .form-message.error {{
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
                display: block;
            }}

            .ok-button {{
                padding: 12px 40px;
                background: #e535ab;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.2s;
                font-family: inherit;
            }}

            .ok-button:hover {{
                background: #c72d93;
            }}

            @media (max-width: 768px) {{
                .container {{
                    padding: 20px 15px;
                }}

                .product-layout {{
                    grid-template-columns: 1fr;
                    padding: 25px;
                }}

                .modal-content {{
                    margin: 10% auto;
                    padding: 30px 20px;
                }}
            }}

                .current-group-status {{
                    background: #fff3cd;
                    border-left: 4px solid #e535ab;
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    font-size: 15px;
                    line-height: 1.6;
                    color: #1a202c;
                }}

                .current-group-status strong {{
                    color: #e535ab;
                }}

                /* Галерея продуктов */
                .products-gallery {{
                    background: white;
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    margin-top: 40px;
                }}

                .products-gallery h3 {{
                    font-size: 24px;
                    margin-bottom: 25px;
                    color: #1a202c;
                    text-align: center;
                }}

                .products-gallery-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: 20px;
                }}

                .product-gallery-card {{
                    text-decoration: none;
                    color: inherit;
                    display: block;
                    border-radius: 12px;
                    overflow: hidden;
                    transition: all 0.3s ease;
                    background: white;
                    border: 1px solid #e2e8f0;
                }}

                .product-gallery-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 8px 16px rgba(229, 53, 171, 0.2);
                    border-color: #e535ab;
                }}

                .product-gallery-photo {{
                    width: 100%;
                    aspect-ratio: 4/5;
                    overflow: hidden;
                }}

                .product-gallery-photo img {{
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                }}

                .product-gallery-info {{
                    padding: 15px;
                }}

                .product-gallery-talent {{
                    font-size: 12px;
                    color: #718096;
                    margin-bottom: 5px;
                }}

                .product-gallery-name {{
                    font-size: 15px;
                    font-weight: 600;
                    color: #1a202c;
                    margin-bottom: 8px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }}

                .product-gallery-price {{
                    font-size: 16px;
                    font-weight: 600;
                    color: #e535ab;
                    margin-bottom: 10px;
                }}

                .product-gallery-progress {{
                    margin-top: 8px;
                }}

                .slots-info-small {{
                    font-size: 11px;
                    color: #718096;
                    margin-top: 5px;
                }}
        </style>

        <script>
            const PRODUCT_SLUG = '{product['slug']}';
            const PRODUCT_PRICE = {product['price_ils']};
            const ALLPAY_BASE_URL = 'https://allpay.to/~yallabalagan/donate-yalla';

            // Ключи для localStorage
            const STORAGE_KEY_PURCHASE = 'purchase_form_data';
            const STORAGE_KEY_TELEGRAM = 'telegram_form_data';

            // Сохранение данных формы
            function saveFormData(formId, storageKey) {{
                const form = document.getElementById(formId);
                const data = {{}};

                const inputs = form.querySelectorAll('input');
                inputs.forEach(input => {{
                    data[input.id] = input.value;
                }});

                localStorage.setItem(storageKey, JSON.stringify(data));
            }}

            // Восстановление данных формы
            function restoreFormData(formId, storageKey) {{
                const savedData = localStorage.getItem(storageKey);
                if (!savedData) return;

                try {{
                    const data = JSON.parse(savedData);
                    const form = document.getElementById(formId);

                    Object.keys(data).forEach(fieldId => {{
                        const input = document.getElementById(fieldId);
                        if (input && data[fieldId]) {{
                            input.value = data[fieldId];
                        }}
                    }});
                }} catch (e) {{
                    console.error('Error restoring form data:', e);
                }}
            }}

            // Очистка сохраненных данных
            function clearFormData(storageKey) {{
                localStorage.removeItem(storageKey);
            }}

            // Инициализация автосохранения для формы
            function initAutoSave(formId, storageKey) {{
                const form = document.getElementById(formId);
                const inputs = form.querySelectorAll('input');

                inputs.forEach(input => {{
                    input.addEventListener('input', () => {{
                        saveFormData(formId, storageKey);
                    }});
                }});
            }}

            function openPurchaseModal() {{
                document.getElementById('purchaseModal').style.display = 'block';
                document.body.style.overflow = 'hidden';
                restoreFormData('purchaseForm', STORAGE_KEY_PURCHASE);
            }}

            function closePurchaseModal() {{
                document.getElementById('purchaseModal').style.display = 'none';
                document.body.style.overflow = 'auto';
                // НЕ очищаем форму и НЕ удаляем из localStorage - данные сохраняются
                document.getElementById('formMessage').className = 'form-message';
                document.getElementById('formMessage').textContent = '';
            }}

            function submitPurchase(event) {{
                event.preventDefault();

                const formMessage = document.getElementById('formMessage');

                // Валидация Telegram (только если заполнено)
                const telegram = document.getElementById('buyer_telegram').value.trim();
                if (telegram && !telegram.startsWith('@')) {{
                    formMessage.className = 'form-message error';
                    formMessage.textContent = 'Telegram должен начинаться с @ (или оставьте пустым)';
                    return;
                }}

                // Валидация email
                const email = document.getElementById('buyer_email').value.trim();
                if (!email || !email.includes('@')) {{
                    formMessage.className = 'form-message error';
                    formMessage.textContent = 'Укажите корректный email';
                    return;
                }}

                // Собираем данные
                const name = document.getElementById('buyer_name').value.trim();

                // Формируем add_field: "product-slug,telegram"
                const addField = telegram ? `${{PRODUCT_SLUG}},${{telegram}}` : PRODUCT_SLUG + ',';

                // Формируем URL для AllPay
                const params = new URLSearchParams({{
                    amount: PRODUCT_PRICE,
                    client_name: name,
                    client_email: email,
                    add_field: addField
                }});

                const allpayUrl = `${{ALLPAY_BASE_URL}}?${{params.toString()}}`;

                console.log('Redirecting to AllPay:', allpayUrl);

                // Очищаем сохраненные данные перед редиректом
                clearFormData(STORAGE_KEY_PURCHASE);

                // Редирект на AllPay
                window.location.href = allpayUrl;
            }}

            // Telegram Stars функции
            function openTelegramModal() {{
                document.getElementById('telegramModal').style.display = 'block';
                document.body.style.overflow = 'hidden';
                restoreFormData('telegramForm', STORAGE_KEY_TELEGRAM);
            }}

            function closeTelegramModal() {{
                document.getElementById('telegramModal').style.display = 'none';
                document.body.style.overflow = 'auto';
                // НЕ очищаем форму и НЕ удаляем из localStorage - данные сохраняются
                document.getElementById('telegramFormMessage').className = 'form-message';
                document.getElementById('telegramFormMessage').textContent = '';
            }}

            // Обновляем обработку клика вне модалки для обеих модалок
            window.onclick = function(event) {{
                const purchaseModal = document.getElementById('purchaseModal');
                const telegramModal = document.getElementById('telegramModal');

                if (event.target === purchaseModal) {{
                    closePurchaseModal();
                }}
                if (event.target === telegramModal) {{
                    closeTelegramModal();
                }}
            }}

            async function submitTelegramPayment(event) {{
                event.preventDefault();

                const formMessage = document.getElementById('telegramFormMessage');
                const submitButton = document.getElementById('tg_submitButton');

                // Валидация Telegram (только если заполнено)
                const telegram = document.getElementById('tg_buyer_telegram').value.trim();
                if (telegram && !telegram.startsWith('@')) {{
                    formMessage.className = 'form-message error';
                    formMessage.textContent = 'Telegram должен начинаться с @ (или оставьте пустым)';
                    return;
                }}

                // Валидация email
                const email = document.getElementById('tg_buyer_email').value.trim();
                if (!email || !email.includes('@')) {{
                    formMessage.className = 'form-message error';
                    formMessage.textContent = 'Укажите корректный email';
                    return;
                }}

                // Валидация кода
                const code = document.getElementById('tg_code').value.trim();
                if (!code) {{
                    formMessage.className = 'form-message error';
                    formMessage.textContent = 'Введите код из Telegram';
                    return;
                }}

                // Блокируем кнопку
                submitButton.disabled = true;
                submitButton.textContent = 'Обработка...';

                // Собираем данные
                const data = {{
                    payment_type: 'telegram',
                    product_slug: PRODUCT_SLUG,
                    buyer_name: document.getElementById('tg_buyer_name').value.trim(),
                    buyer_email: email,
                    buyer_telegram: telegram,
                    buyer_phone: document.getElementById('tg_buyer_phone').value.trim(),
                    tg_code: code
                }};

                try {{
                    // Отправляем запрос на лямбду
                    const response = await fetch('https://jw6u5akii7.execute-api.eu-north-1.amazonaws.com/prod/telegram-payment', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify(data)
                    }});

                    const result = await response.json();

                    if (response.ok && result.success) {{
                        // Успех! Очищаем сохраненные данные
                        clearFormData(STORAGE_KEY_TELEGRAM);

                        formMessage.className = 'form-message success';
                        formMessage.innerHTML = `
                            <strong>Спасибо за поддержку!</strong><br>
                            В ближайшее время вам придет письмо с деталями вашего заказа, и вскоре с вами свяжутся по поводу его выполнения!<br><br>
                            Если у вас есть вопросы, пишите на yalla@yallabalagan.org или в ТГ Льву: @excremental
                        `;

                        // Скрываем форму
                        document.getElementById('telegramForm').style.display = 'none';

                        // Через 5 секунд перезагружаем страницу чтобы обновить счётчик
                        setTimeout(() => {{
                            window.location.reload();
                        }}, 5000);
                    }} else {{
                        // Ошибка
                        formMessage.className = 'form-message error';
                        formMessage.textContent = result.error || 'Произошла ошибка. Попробуйте снова.';

                        // Разблокируем кнопку
                        submitButton.disabled = false;
                        submitButton.textContent = 'Подтвердить оплату';
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    formMessage.className = 'form-message error';
                    formMessage.textContent = 'Произошла ошибка соединения. Попробуйте снова.';

                    // Разблокируем кнопку
                    submitButton.disabled = false;
                    submitButton.textContent = 'Подтвердить оплату';
                }}
            }}

            // Инициализация автосохранения при загрузке страницы
            window.addEventListener('DOMContentLoaded', () => {{
                initAutoSave('purchaseForm', STORAGE_KEY_PURCHASE);
                initAutoSave('telegramForm', STORAGE_KEY_TELEGRAM);
            }});
        </script>
    </head>
    <body>
        <div class="container">
            <div class="breadcrumbs">
                <a href="/">Главная</a> → 
                <a href="/talent/{talent['slug']}/">{talent['name']}</a> → 
                {product['name']}
            </div>

            <a href="/talent/{talent['slug']}/" class="back-button">
                ← Назад к {talent['name']}
            </a>

            <div class="product-layout">
                <div class="product-images">
                    <div class="product-image">
                        <img src="{product['photo_url']}" alt="{product['name']}">
                    </div>
                    {gallery_html}
                </div>

                <div class="product-details">
                    <h1>{product['name']}</h1>
                    <span class="product-type">{type_name}</span>

                    <div class="product-price">₪{product['price_ils']}</div>

                    <div class="product-info">
                        <div class="info-item">
                            <span class="info-label">От кого:</span>
                            <span class="info-value">{talent['name']}</span>
                        </div>
                        {group_info_html}
                    </div>

                    {current_group_html}

                    <div class="progress-section">
                        <div class="progress-text">
                            <span>Продано: {product['sold_slots']} из {product['total_slots']}</span>
                            <span>{percentage}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {percentage}%"></div>
                        </div>
                        <div class="availability{'limited' if available_slots <= 3 else ''}">
                            {'⚠️ Осталось всего ' + str(available_slots) + ' ' + get_word_form(available_slots, 'место', 'места', 'мест') + '!' if available_slots <= 3 else 'Доступно: ' + str(available_slots) + ' ' + get_word_form(available_slots, 'место', 'места', 'мест')}
                        </div>
                    </div>

                    <div class="description-section">
                        <h3>Описание</h3>
                        {full_desc_html}
                    </div>

                    <div class="description-section">
                        <h3>Что вы получите</h3>
                        {what_you_get_html}
                    </div>

                    <div class="payment-buttons">
                        <button class="purchase-button" onclick="openPurchaseModal()" {'disabled' if available_slots == 0 else ''}>
                            {('Все места заняты' if available_slots == 0 else 'Купить ₪' + str(product['price_ils']))}
                        </button>

                        {f'''
                        <div class="payment-divider"><span>или</span></div>
                        <button class="telegram-button" onclick="openTelegramModal()" {'disabled' if available_slots == 0 or not product.get('tg_code') else ''}>
                            ⭐ Оплатить звёздами Telegram ({product['price_stars']} ⭐)
                        </button>
                        ''' if product.get('tg_code') and product.get('price_stars') else ''}
                    </div>                    
                </div>
            </div>
        </div>

        {products_gallery_html}

        <footer class="site-footer">
            {footer_html}
        </footer>


        <!-- Модалка покупки -->
        <div id="purchaseModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="closePurchaseModal()">&times;</span>
                <h2>Оформление заявки</h2>

                <div id="formMessage" class="form-message"></div>

                <form id="purchaseForm" onsubmit="submitPurchase(event)">
                    <div class="form-group">
                        <label for="buyer_name">Ваше имя *</label>
                        <input type="text" id="buyer_name" name="buyer_name" required>
                    </div>

                    <div class="form-group">
                        <label for="buyer_email">Email *</label>
                        <input type="email" id="buyer_email" name="buyer_email" required>
                    </div>

                    <div class="form-group">
                        <label for="buyer_telegram">Telegram (необязательно)</label>
                        <input type="text" id="buyer_telegram" name="buyer_telegram" placeholder="@username">
                        <small>Если укажете - начните с @</small>
                    </div>

                    <div class="form-group">
                        <label for="buyer_phone">Телефон (необязательно)</label>
                        <input type="tel" id="buyer_phone" name="buyer_phone">
                        <small>На случай если нужно будет связаться</small>
                    </div>

                    <button type="submit" class="submit-button" id="submitButton">
                        Перейти к оплате ₪{product['price_ils']}
                    </button>
                </form>
            </div>
        </div>

        <!-- Модалка Telegram Stars -->
        <div id="telegramModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="closeTelegramModal()">&times;</span>
                <h2>Оплата звёздами Telegram</h2>

                <div id="telegramFormMessage" class="form-message"></div>

                <form id="telegramForm" onsubmit="submitTelegramPayment(event)">
                    <div class="form-group">
                        <label for="tg_buyer_name">Ваше имя *</label>
                        <input type="text" id="tg_buyer_name" name="tg_buyer_name" required>
                    </div>

                    <div class="form-group">
                        <label for="tg_buyer_email">Email *</label>
                        <input type="email" id="tg_buyer_email" name="tg_buyer_email" required>
                    </div>

                    <div class="form-group">
                        <label for="tg_buyer_telegram">Telegram (необязательно)</label>
                        <input type="text" id="tg_buyer_telegram" name="tg_buyer_telegram" placeholder="@username">
                        <small>Если укажете - начните с @</small>
                    </div>

                    <div class="form-group">
                        <label for="tg_buyer_phone">Телефон (необязательно)</label>
                        <input type="tel" id="tg_buyer_phone" name="tg_buyer_phone">
                        <small>На случай если нужно будет связаться</small>
                    </div>

                    <div class="form-group">
                        <label for="tg_code">Код из Telegram *</label>
                        <input type="text" id="tg_code" name="tg_code" required placeholder="Введите код из поста">
                        <small>
                            <a href="{product['tg_post_link']}" target="_blank" style="color: #0088cc; text-decoration: underline;">
                                Получить код в Telegram →
                            </a>
                        </small>
                    </div>

                    <button type="submit" class="submit-button" id="tg_submitButton">
                        Подтвердить оплату
                    </button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """

    return html


def get_type_name(type_str):
    """Переводит тип товара на русский"""
    return {
        'Individual': 'Персональный',
        'Group': 'Групповой'
    }.get(type_str, type_str)


def get_word_form(number, one, two, five):
    """Склонение слов (1 место, 2 места, 5 мест)"""
    n = abs(number) % 100
    n1 = n % 10
    if n > 10 and n < 20:
        return five
    if n1 > 1 and n1 < 5:
        return two
    if n1 == 1:
        return one
    return five


def lambda_handler(event, context):
    """Main handler"""
    print("Starting donate site generation...")

    try:
        # Получаем данные из Notion
        talents = get_active_talents()
        products = get_active_products()

        # Создаем словарь талантов для быстрого поиска
        talents_dict = {t['id']: t for t in talents}

        # Считаем собранную сумму
        total_raised = calculate_total_raised(products)
        print(f"Total raised: ₪{total_raised:,}")

        # Генерируем главную страницу
        index_html = generate_index_page(talents, products, total_raised)
        upload_to_s3('index.html', index_html)

        # Генерируем страницы талантов
        for talent in talents:
            talent_html = generate_talent_page(talent, products, talents)
            upload_to_s3(f"talent/{talent['slug']}/index.html", talent_html)

        # Генерируем страницы товаров
        for product in products:
            if product['talent_ids'] and product['talent_ids'][0] in talents_dict:
                talent = talents_dict[product['talent_ids'][0]]
                product_html = generate_product_page(product, talent, products, talents)
                upload_to_s3(f"product/{product['slug']}/index.html", product_html)
            else:
                print(f"Warning: Talent not found for product {product['name']}")

        # TODO: Генерация страницы активации

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Site generated successfully',
                'talents': len(talents),
                'products': len(products),
                'total_raised': total_raised
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }