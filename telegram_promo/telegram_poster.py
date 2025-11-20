"""
Скрипт для постинга скриншотов в Telegram
"""

import os
import time
import requests
from pathlib import Path
from collections import defaultdict
from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError, RetryAfter
import asyncio
import config


def get_text_from_rich_text(rich_text_array):
    """Извлекает текст из Notion rich_text"""
    if not rich_text_array:
        return ""
    return "".join([t.get('plain_text', '') for t in rich_text_array])


def notion_headers():
    """Возвращает заголовки для Notion API"""
    return {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": config.NOTION_VERSION
    }


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
        return {}

    pages = response.json().get('results', [])
    talents_dict = {}

    print(f"  📊 Fetched {len(pages)} talents from Notion")

    for page in pages:
        props = page['properties']
        slug = get_text_from_rich_text(props.get('Slug', {}).get('rich_text', []))
        name = get_text_from_rich_text(props.get('Name', {}).get('title', []))

        if slug:
            talents_dict[slug] = {
                'name': name,
                'slug': slug
            }
            print(f"  ✓ Loaded: {slug} -> {name}")
        else:
            print(f"  ⚠️  Skipped talent without slug: {name}")

    print(f"  📋 Total talents in dict: {len(talents_dict)}")
    return talents_dict


def group_screenshots_by_talent(talents_dict):
    """
    Группирует скриншоты по талантам

    Args:
        talents_dict: dict с информацией о талантах {slug: {...}}

    Returns:
        dict: {talent_slug: [screenshot_paths]}
    """
    screenshots_dir = Path(config.SCREENSHOTS_DIR)

    if not screenshots_dir.exists():
        print(f"❌ Screenshots directory not found: {screenshots_dir}")
        return {}

    screenshots_by_talent = defaultdict(list)

    # Проходим по всем PNG файлам
    for screenshot_path in screenshots_dir.glob("*.png"):
        filename = screenshot_path.stem  # имя без расширения

        # Формат: {talent_slug}_{product_slug}.png
        # Находим подходящий talent_slug среди известных из Notion
        matched_slug = None
        for talent_slug in talents_dict.keys():
            # Проверяем, начинается ли имя файла с этого slug
            if filename.startswith(talent_slug + '_'):
                matched_slug = talent_slug
                break

        if matched_slug:
            screenshots_by_talent[matched_slug].append(str(screenshot_path))
        else:
            print(f"  ⚠️  Could not match screenshot to talent: {filename}")

    print(f"  📸 Screenshot slugs matched: {list(screenshots_by_talent.keys())}")
    return dict(screenshots_by_talent)


async def post_to_telegram(bot, chat_id, talent_info, screenshot_paths, max_retries=3):
    """
    Постит скриншоты в Telegram для одного таланта

    Args:
        bot: Telegram Bot instance
        chat_id: ID чата куда постить
        talent_info: dict с информацией о таланте
        screenshot_paths: list путей к скриншотам
        max_retries: максимальное количество попыток при flood control
    """
    # Получаем первое имя (первое слово из полного имени)
    first_name = talent_info['name'].split()[0] if talent_info['name'] else talent_info['name']

    # Формируем текст сообщения
    message_text = config.MESSAGE_TEMPLATE.format(
        talent_name=first_name,
        site_url=config.DONATE_SITE_URL,
        talent_slug=talent_info['slug']
    )

    print(f"  📤 Posting {len(screenshot_paths)} screenshots for {talent_info['name']}")

    for attempt in range(max_retries):
        try:
            if len(screenshot_paths) == 1:
                # Одна фотография - отправляем с текстом
                with open(screenshot_paths[0], 'rb') as photo:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=message_text
                    )
            else:
                # Несколько фотографий - отправляем media group
                media_group = []

                for idx, path in enumerate(screenshot_paths):
                    with open(path, 'rb') as photo:
                        # Первое фото с caption
                        if idx == 0:
                            media_group.append(
                                InputMediaPhoto(media=photo.read(), caption=message_text)
                            )
                        else:
                            media_group.append(
                                InputMediaPhoto(media=photo.read())
                            )

                await bot.send_media_group(
                    chat_id=chat_id,
                    media=media_group
                )

            print(f"  ✅ Posted successfully!")
            return True

        except RetryAfter as e:
            retry_after = e.retry_after
            print(f"  ⚠️  Flood control: waiting {retry_after} seconds...")
            await asyncio.sleep(retry_after)
            # Попробуем еще раз после ожидания
            continue

        except TelegramError as e:
            print(f"  ❌ Telegram error: {e}")
            return False
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False

    print(f"  ❌ Failed after {max_retries} attempts")
    return False


async def main():
    """Главная функция"""
    print("=" * 60)
    print("📱 Starting Telegram posting")
    print("=" * 60)

    # Проверяем конфигурацию
    if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ ERROR: Telegram bot token not configured!")
        print("   Set TELEGRAM_BOT_TOKEN in config.py or environment variable")
        return

    if not config.CHAT_ID or config.CHAT_ID == 'YOUR_CHAT_ID_HERE':
        print("❌ ERROR: Telegram chat ID not configured!")
        print("   Set CHAT_ID in config.py or environment variable")
        return

    # Получаем информацию о талантах из Notion
    print("\n📥 Fetching talent information from Notion...")
    talents_info = get_active_talents()

    if not talents_info:
        print("❌ Could not fetch talents from Notion!")
        return

    # Проверяем наличие скриншотов и группируем по талантам
    print("\n📸 Grouping screenshots by talents...")
    screenshots_by_talent = group_screenshots_by_talent(talents_info)

    if not screenshots_by_talent:
        print("❌ No screenshots found!")
        print(f"   Run screenshot_products.py first to generate screenshots")
        return

    print(f"✅ Found screenshots for {len(screenshots_by_talent)} talents")

    # Создаем бота
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)

    # Постим для каждого таланта
    print(f"\n📤 Starting posting to chat {config.CHAT_ID}...")
    posted_count = 0
    failed_count = 0

    for talent_slug, screenshot_paths in screenshots_by_talent.items():
        # Получаем информацию о таланте
        talent_info = talents_info.get(talent_slug)

        if not talent_info:
            print(f"\n⚠️  Talent not found in Notion: {talent_slug}")
            print(f"   Screenshots: {len(screenshot_paths)}")
            failed_count += 1
            continue

        print(f"\n[{posted_count + failed_count + 1}/{len(screenshots_by_talent)}] {talent_info['name']}")

        # Постим в Telegram
        success = await post_to_telegram(
            bot,
            config.CHAT_ID,
            talent_info,
            screenshot_paths
        )

        if success:
            posted_count += 1
        else:
            failed_count += 1

        # Задержка между постами
        if posted_count + failed_count < len(screenshots_by_talent):
            print(f"  ⏳ Waiting {config.POST_DELAY}s before next post...")
            await asyncio.sleep(config.POST_DELAY)

    # Итоговая статистика
    print("\n" + "=" * 60)
    print("✅ COMPLETED!")
    print("=" * 60)
    print(f"📊 Statistics:")
    print(f"  - Successfully posted: {posted_count}")
    print(f"  - Failed: {failed_count}")
    print(f"  - Total: {len(screenshots_by_talent)}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
