"""
Скрипт для создания скриншотов карточек товаров с сайта donate.yallabalagan.org
"""

import os
import time
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright
import config


def notion_headers():
    """Возвращает заголовки для Notion API"""
    return {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": config.NOTION_VERSION
    }


def get_text_from_rich_text(rich_text_array):
    """Извлекает текст из Notion rich_text"""
    if not rich_text_array:
        return ""
    return "".join([t.get('plain_text', '') for t in rich_text_array])


def get_active_talents():
    """Получает все активные таланты из Notion"""
    response = requests.post(
        f"{config.NOTION_API_URL}/databases/{config.TALENTS_DB_ID}/query",
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
        print(f"❌ Error fetching talents: {response.text}")
        return []

    pages = response.json().get('results', [])
    talents = []

    for page in pages:
        props = page['properties']

        talent = {
            'id': page['id'],
            'name': get_text_from_rich_text(props.get('Name', {}).get('title', [])),
            'slug': get_text_from_rich_text(props.get('Slug', {}).get('rich_text', []))
        }

        talents.append(talent)

    print(f"✅ Found {len(talents)} active talents")
    return talents


def get_active_products():
    """Получает все активные товары из Notion"""
    response = requests.post(
        f"{config.NOTION_API_URL}/databases/{config.PRODUCTS_DB_ID}/query",
        headers=notion_headers(),
        json={
            "filter": {
                "property": "Status",
                "select": {
                    "equals": "Active"
                }
            }
        }
    )

    if response.status_code != 200:
        print(f"❌ Error fetching products: {response.text}")
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
            'talent_ids': talent_ids
        }

        products.append(product)

    print(f"✅ Found {len(products)} active products")
    return products


def screenshot_product_cards(talent, products):
    """
    Делает скриншоты всех карточек товаров для данного таланта

    Args:
        talent: dict с данными таланта (id, name, slug)
        products: list всех продуктов для фильтрации

    Returns:
        list: пути к созданным скриншотам
    """
    # Фильтруем товары этого таланта
    talent_products = [p for p in products if talent['id'] in p['talent_ids']]

    if not talent_products:
        print(f"  ⚠️  No products for {talent['name']}")
        return []

    print(f"  📸 Screenshotting {len(talent_products)} products for {talent['name']}")

    screenshot_paths = []

    with sync_playwright() as p:
        # Запускаем браузер
        browser = p.chromium.launch(headless=True)

        # Создаем страницу с мобильными настройками (эмуляция iPhone)
        page = browser.new_page(
            viewport={'width': config.VIEWPORT_WIDTH, 'height': config.VIEWPORT_HEIGHT},
            user_agent=config.USER_AGENT,
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3  # Retina display
        )

        # Открываем страницу таланта
        url = f"{config.DONATE_SITE_URL}/talent/{talent['slug']}/"
        print(f"  🌐 Opening {url}")

        try:
            page.goto(url, wait_until='networkidle', timeout=30000)
            time.sleep(2)  # Дополнительная задержка для полной загрузки

            # Находим все карточки продуктов
            product_cards = page.query_selector_all('.product-card')

            if not product_cards:
                print(f"  ⚠️  No product cards found on page")
                browser.close()
                return []

            print(f"  ✓ Found {len(product_cards)} product cards on page")

            # Скриншотим каждую карточку
            for idx, card in enumerate(product_cards):
                try:
                    # Пытаемся определить slug продукта из ссылки
                    link = card.query_selector('a.product-link')
                    product_slug = talent_products[idx]['slug'] if idx < len(talent_products) else f"product_{idx}"

                    if link:
                        href = link.get_attribute('href')
                        if '/product/' in href:
                            product_slug = href.split('/product/')[1].strip('/')

                    # Путь к файлу скриншота
                    screenshot_path = os.path.join(
                        config.SCREENSHOTS_DIR,
                        f"{talent['slug']}_{product_slug}.png"
                    )

                    # Скриншот карточки
                    card.screenshot(path=screenshot_path)
                    screenshot_paths.append(screenshot_path)
                    print(f"    ✓ Screenshot saved: {screenshot_path}")

                    time.sleep(config.SCREENSHOT_DELAY)

                except Exception as e:
                    print(f"    ❌ Error screenshotting card {idx}: {e}")

        except Exception as e:
            print(f"  ❌ Error loading page: {e}")

        finally:
            browser.close()

    return screenshot_paths


def main():
    """Главная функция"""
    print("=" * 60)
    print("🚀 Starting product screenshots generation")
    print("=" * 60)

    # Создаем папку для скриншотов если её нет
    Path(config.SCREENSHOTS_DIR).mkdir(exist_ok=True)
    print(f"📁 Screenshots directory: {os.path.abspath(config.SCREENSHOTS_DIR)}")

    # Проверяем наличие Notion credentials
    if not config.NOTION_TOKEN or not config.TALENTS_DB_ID:
        print("❌ ERROR: Notion credentials not configured!")
        print("   Set NOTION_TOKEN and TALENTS_DB_ID environment variables")
        return

    # Получаем данные из Notion
    print("\n📥 Fetching data from Notion...")
    talents = get_active_talents()
    products = get_active_products()

    if not talents:
        print("❌ No talents found!")
        return

    if not products:
        print("❌ No products found!")
        return

    # Создаем скриншоты для каждого таланта
    print(f"\n📸 Starting screenshots for {len(talents)} talents...")
    all_screenshots = {}

    for idx, talent in enumerate(talents, 1):
        print(f"\n[{idx}/{len(talents)}] Processing: {talent['name']}")
        screenshots = screenshot_product_cards(talent, products)

        if screenshots:
            all_screenshots[talent['slug']] = {
                'talent': talent,
                'screenshots': screenshots
            }

    # Итоговая статистика
    print("\n" + "=" * 60)
    print("✅ COMPLETED!")
    print("=" * 60)
    print(f"📊 Statistics:")
    print(f"  - Talents processed: {len(all_screenshots)}")
    total_screenshots = sum(len(data['screenshots']) for data in all_screenshots.values())
    print(f"  - Total screenshots: {total_screenshots}")
    print(f"  - Location: {os.path.abspath(config.SCREENSHOTS_DIR)}")
    print("\n💡 Next step: Run telegram_poster.py to post to Telegram")
    print("=" * 60)


if __name__ == "__main__":
    main()
