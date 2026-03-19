"""
Скрипт миграции билетов из двух старых эвентов в новый большой зал.

Что делает:
  1. Читает migration_plan.csv (сгенерирован заранее через анализ)
  2. Для каждого старого заказа создаёт НОВЫЙ заказ в новом эвенте:
     - Новый order_id
     - Новый event_id
     - Те же данные покупателя и оплаты
     - Новые номера мест (из плана)
     - Те же QR-коды (строки), только seat_id обновлён
  3. Обновляет available в ticket_types нового эвента
  4. Записывает лог всех созданных заказов

Что НЕ делает:
  - Не трогает старые заказы
  - Не отменяет старые эвенты
  - Не отправляет уведомления

Запуск:
  python3 scripts/migrate_event.py [--dry-run]

  --dry-run  Только вывод без записи в DynamoDB
"""

import argparse
import csv
import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import boto3
from decimal import Decimal

# ── Путь к корню ticket-service ────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

NEW_EVENT_ID = "196ff109-c2aa-417d-8aec-5a0f3fa09731"
OLD_EVENT_IDS = {
    "17:00": "18ea42fa-674a-4c58-b9ae-517c9fe20353",
    "20:00": "71a600db-0f55-42b1-b2cb-e3f1af9b45e4",
}
PLAN_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migration_plan.csv")
LOG_PATH  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migration_log.json")

REGION = "eu-north-1"
ORDERS_TABLE  = os.environ.get("ORDERS_TABLE",  "yallabalagan-orders")
EVENTS_TABLE  = os.environ.get("EVENTS_TABLE",  "yallabalagan-events")


# ── DynamoDB helpers ────────────────────────────────────────────────────────
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def dynamodb_resource():
    return boto3.resource("dynamodb", region_name=REGION)


def get_order(table, order_id: str):
    resp = table.get_item(Key={"PK": f"ORDER#{order_id}", "SK": "METADATA"})
    return resp.get("Item")


def get_event(table, event_id: str):
    resp = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"})
    return resp.get("Item")


def check_already_migrated(orders_table, old_order_id: str) -> bool:
    """Проверяем, не создан ли уже новый заказ для этого старого."""
    resp = orders_table.query(
        IndexName="EventIndex",
        KeyConditionExpression="event_id = :eid",
        FilterExpression="migrated_from_order_id = :oid",
        ExpressionAttributeValues={
            ":eid": NEW_EVENT_ID,
            ":oid": old_order_id,
        },
    )
    return len(resp.get("Items", [])) > 0


# ── Читаем план миграции ─────────────────────────────────────────────────────
def load_migration_plan(path: str) -> dict:
    """
    Возвращает: {(old_order_id, event_label): [(old_grid_key, new_grid_key, new_row, new_seat), ...]}
    """
    plan = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["Order ID"], row["Шоу"])
            plan[key].append({
                "old_grid_key":  row["Новый grid_key"],   # Внимание: колонка "Новый grid_key"
                # Нам нужен старый grid_key чтобы матчить QR — читаем ниже
                "new_grid_key":  row["Новый grid_key"],
                "new_row":       int(row["Новый ряд"]),
                "new_seat":      int(row["Новое место"]),
                "old_row":       int(row["Старый ряд"]),
                "old_seat":      int(row["Старое место"]),
                "type_name":     row["Тип билета"],
            })
    return plan


def load_migration_plan_with_old_keys(path: str) -> dict:
    """
    Читает план и строит маппинг old_grid_key → new_grid_key для каждого заказа.
    Также возвращает словарь (order_id, event) → список seat-записей.
    Для восстановления old_grid_key используем данные из старых заказов напрямую.
    """
    rows_by_order = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows_by_order[(row["Order ID"], row["Шоу"])].append(row)
    return rows_by_order


# ── Строим новый заказ ───────────────────────────────────────────────────────
def build_new_order(old_order: dict, seat_map: dict, new_order_id: str) -> dict:
    """
    old_order:    item из DynamoDB (старый заказ)
    seat_map:     {old_grid_key: new_grid_key}  — маппинг мест
    new_order_id: новый UUID

    Возвращает готовый item для put_item в orders table.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── Обновляем purchased_seats в tickets ──────────────────────────────
    new_tickets = []
    for ticket in old_order.get("tickets", []):
        old_seats = ticket.get("purchased_seats", [])
        new_seats = [seat_map.get(s, s) for s in old_seats]
        new_tickets.append({**ticket, "purchased_seats": new_seats})

    # ── Обновляем seat_id в qr_codes (только не-cancelled) ──────────────
    new_qr_codes = []
    for qr in old_order.get("qr_codes", []):
        if qr.get("cancelled", False):
            # Cancelled QR пропускаем — в новом заказе их нет
            continue
        old_seat = qr.get("seat_id")
        new_seat = seat_map.get(old_seat, old_seat)
        new_qr_codes.append({**qr, "seat_id": new_seat})

    new_item = {
        "PK":               f"ORDER#{new_order_id}",
        "SK":               "METADATA",
        "order_id":         new_order_id,
        "event_id":         NEW_EVENT_ID,
        "customer":         old_order["customer"],
        "customer_email":   old_order.get("customer_email", old_order["customer"].get("email", "")),
        "tickets":          new_tickets,
        "total_amount":     old_order["total_amount"],
        "currency":         old_order.get("currency", "ILS"),
        "payment":          old_order["payment"],
        "qr_codes":         new_qr_codes,
        "notifications":    {"email_sent": False, "sms_sent": False, "reminder_sent": False},
        "created_at":       now,
        "migrated_from_order_id":   old_order["order_id"],
        "migrated_from_event_id":   old_order["event_id"],
        "migrated_at":              now,
    }

    if old_order.get("coupon_code"):
        new_item["coupon_code"] = old_order["coupon_code"]
    if old_order.get("discount_amount"):
        new_item["discount_amount"] = old_order["discount_amount"]

    return new_item


# ── Обновляем available в новом эвенте ───────────────────────────────────────
def update_event_available(events_table, type_counts: dict, dry_run: bool):
    """
    type_counts: {type_id: count}  — сколько мест мигрировано по каждому типу
    """
    event = get_event(events_table, NEW_EVENT_ID)
    if not event:
        raise RuntimeError(f"New event {NEW_EVENT_ID} not found!")

    ticket_types = event.get("ticket_types", [])
    updated = False
    for tt in ticket_types:
        tid = tt.get("id") or tt.get("type_id")
        if tid in type_counts:
            old_avail = int(tt["available"])
            new_avail = old_avail - type_counts[tid]
            if new_avail < 0:
                raise ValueError(
                    f"Не хватает мест! type_id={tid} available={old_avail} need={type_counts[tid]}"
                )
            print(f"  {tt['name']}: available {old_avail} → {new_avail}")
            tt["available"] = Decimal(str(new_avail))
            updated = True

    if not updated:
        print("  ⚠️  Ни один type_id не совпал, available не обновлён!")
        return

    if dry_run:
        print("  [DRY RUN] Обновление available пропущено")
        return

    events_table.put_item(Item={**event, "ticket_types": ticket_types,
                                "updated_at": datetime.now(timezone.utc).isoformat()})
    print("  ✓ available обновлён в новом эвенте")


# ── Главная логика ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Симуляция без записи в DynamoDB")
    args = parser.parse_args()
    dry_run = args.dry_run

    if dry_run:
        print("=" * 60)
        print("  DRY RUN — никаких изменений в DynamoDB не будет")
        print("=" * 60)

    db = dynamodb_resource()
    orders_table = db.Table(ORDERS_TABLE)
    events_table = db.Table(EVENTS_TABLE)

    # ── Читаем план ──────────────────────────────────────────────────────
    print(f"\n📋 Читаем план: {PLAN_PATH}")
    rows_by_order = load_migration_plan_with_old_keys(PLAN_PATH)
    print(f"   Уникальных заказов в плане: {len(rows_by_order)}")

    # ── Загружаем старые заказы из DynamoDB ──────────────────────────────
    # Собираем все уникальные order_id
    old_order_ids = {order_id for order_id, _ in rows_by_order.keys()}
    print(f"\n📥 Загружаем {len(old_order_ids)} старых заказов из DynamoDB...")

    old_orders = {}
    for order_id in old_order_ids:
        item = get_order(orders_table, order_id)
        if not item:
            print(f"  ⚠️  Заказ {order_id} не найден в DynamoDB, пропускаем")
            continue
        old_orders[order_id] = item
    print(f"   Найдено: {len(old_orders)}")

    # ── Строим seat_map для каждого заказа ───────────────────────────────
    # old_grid_key восстанавливаем из qr_codes старого заказа
    # Логика: qr.seat_id = old_grid_key, план даёт нам new_grid_key для каждого (row, seat)
    # Матчим через (old_row, old_seat) → old_grid_key из OLD_CUSTOM (уже есть в плане через csv)

    # В CSV нет колонки old_grid_key напрямую — но есть Старый ряд / Старое место.
    # Нам нужна обратная map: (disp_row, disp_seat) → grid_key из старого QR.
    # Проще: берём qr.seat_id (это и есть grid_key), и из OLD_CUSTOM смотрим его (row, seat).
    # Тогда матчим csv-строку по (old_row, old_seat) с qr.seat_id через OLD_CUSTOM.

    # Собираем OLD_CUSTOM inline (уже известен)
    OLD_DISPLAY = {}  # grid_key → (disp_row, disp_seat)
    OLD_CUSTOM_DATA = {
        "10-5":(6,11),"10-4":(5,11),"10-3":(4,11),"10-2":(3,11),"10-1":(2,11),"10-0":(1,11),
        "3-0":(1,4),"3-1":(2,4),"3-2":(3,4),"3-3":(4,4),"3-4":(5,4),"3-5":(6,4),
        "3-6":(7,4),"3-7":(8,4),"3-8":(9,4),"3-9":(10,4),
        "7-0":(1,8),"7-1":(2,8),"7-2":(3,8),"7-3":(4,8),"7-4":(5,8),"7-5":(6,8),
        "7-6":(7,8),"7-7":(8,8),"7-8":(9,8),"7-9":(10,8),"7-10":(11,8),
        "10-9":(10,11),"10-8":(9,11),"10-7":(8,11),"10-6":(7,11),"10-10":(11,11),
        "2-0":(1,3),"2-1":(2,3),"2-2":(3,3),"2-3":(4,3),"2-4":(5,3),"2-5":(6,3),
        "2-6":(7,3),"2-7":(8,3),"2-8":(9,3),"2-9":(10,3),"2-10":(11,3),
        "6-0":(1,7),"6-1":(2,7),"6-2":(3,7),"6-3":(4,7),"6-4":(5,7),"6-5":(6,7),
        "6-6":(7,7),"6-7":(8,7),"6-8":(9,7),
        "1-0":(1,2),"1-1":(2,2),"1-2":(3,2),"1-3":(4,2),"1-4":(5,2),"1-5":(6,2),
        "1-6":(7,2),"1-7":(8,2),"1-8":(9,2),"1-9":(10,2),"1-10":(11,2),
        "5-0":(1,6),"5-1":(2,6),"5-2":(3,6),"5-3":(4,6),"5-4":(5,6),"5-5":(6,6),
        "5-6":(7,6),"5-7":(8,6),"5-8":(9,6),"5-9":(10,6),"5-10":(11,6),
        "9-0":(1,10),"9-1":(2,10),"9-2":(3,10),"9-3":(4,10),"9-4":(5,10),"9-5":(6,10),
        "9-6":(7,10),"9-7":(8,10),"9-8":(9,10),"9-9":(10,10),
        "0-0":(1,1),"0-1":(2,1),"0-2":(3,1),"0-3":(4,1),"0-4":(5,1),"0-5":(6,1),
        "0-6":(7,1),"0-7":(8,1),"0-8":(9,1),"0-9":(10,1),"0-10":(11,1),
        "4-0":(1,5),"4-1":(2,5),"4-2":(3,5),"4-3":(4,5),"4-4":(5,5),"4-5":(6,5),
        "4-6":(7,5),"4-7":(8,5),"4-8":(9,5),"4-9":(10,5),"4-10":(11,5),
        "8-0":(1,9),"8-1":(2,9),"8-2":(3,9),"8-3":(4,9),"8-4":(5,9),"8-5":(6,9),
        "8-6":(7,9),"8-7":(8,9),"8-8":(9,9),"8-9":(10,9),"8-10":(11,9),
        "6-9":(10,7),"6-10":(11,7),
        "3-10":(11,4),
        "9-10":(11,10),
    }
    # OLD_CUSTOM_DATA stores (display_seat, display_row) but CSV uses (display_row, display_seat)
    # So swap tuple to get correct lookup: (disp_row, disp_seat) → old_grid_key
    DISPLAY_TO_GRID = {(v[1], v[0]): k for k, v in OLD_CUSTOM_DATA.items()}

    # ── Итерируем по заказам ─────────────────────────────────────────────
    log_entries = []
    skipped = []
    created_count = 0

    # Считаем сколько мест мигрируем по типам (для обновления available)
    # Нужны type_id из нового эвента
    new_event = get_event(events_table, NEW_EVENT_ID)
    if not new_event:
        print(f"❌ Новый эвент {NEW_EVENT_ID} не найден!")
        sys.exit(1)
    type_name_to_id = {tt["name"]: (tt.get("id") or tt.get("type_id"))
                       for tt in new_event.get("ticket_types", [])}
    migrated_type_counts = defaultdict(int)  # type_id → count

    print(f"\n🚀 Создаём новые заказы...")

    for (old_order_id, event_label), plan_rows in rows_by_order.items():
        old_order = old_orders.get(old_order_id)
        if not old_order:
            skipped.append({"order_id": old_order_id, "reason": "not found in DB"})
            continue

        # Идемпотентность: уже мигрирован?
        if check_already_migrated(orders_table, old_order_id):
            print(f"  ⏭  {old_order_id[:8]} уже мигрирован, пропускаем")
            skipped.append({"order_id": old_order_id, "reason": "already migrated"})
            continue

        # Строим seat_map: old_grid_key → new_grid_key
        seat_map = {}
        for row in plan_rows:
            old_disp = (int(row["Старый ряд"]), int(row["Старое место"]))
            old_gk = DISPLAY_TO_GRID.get(old_disp)
            if not old_gk:
                print(f"  ⚠️  Не найден grid_key для {old_disp} в заказе {old_order_id[:8]}")
                continue
            seat_map[old_gk] = row["Новый grid_key"]
            # Считаем для обновления available
            type_id = type_name_to_id.get(row["Тип билета"])
            if type_id:
                migrated_type_counts[type_id] += 1

        new_order_id = str(uuid.uuid4())
        new_item = build_new_order(old_order, seat_map, new_order_id)

        customer_name = old_order.get("customer", {}).get("name", "?")
        new_seats_preview = list(seat_map.values())[:3]

        if dry_run:
            print(f"  [DRY] {old_order_id[:8]} ({event_label}) → {new_order_id[:8]}"
                  f"  {customer_name[:20]}  seats→{new_seats_preview}")
        else:
            orders_table.put_item(Item=new_item)
            print(f"  ✓ {old_order_id[:8]} ({event_label}) → {new_order_id[:8]}"
                  f"  {customer_name[:20]}")

        log_entries.append({
            "old_order_id":   old_order_id,
            "new_order_id":   new_order_id,
            "event_label":    event_label,
            "customer":       customer_name,
            "seat_map":       seat_map,
        })
        created_count += 1

    # ── Обновляем available в новом эвенте ────────────────────────────────
    print(f"\n📊 Обновляем available в новом эвенте ({NEW_EVENT_ID[:8]}...):")
    update_event_available(events_table, migrated_type_counts, dry_run)

    # ── Сохраняем лог ─────────────────────────────────────────────────────
    log = {
        "run_at":       datetime.now(timezone.utc).isoformat(),
        "dry_run":      dry_run,
        "created":      created_count,
        "skipped":      len(skipped),
        "skipped_list": skipped,
        "entries":      log_entries,
    }
    if not dry_run:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2, cls=DecimalEncoder)
        print(f"\n📝 Лог сохранён: {LOG_PATH}")

    print(f"\n{'='*60}")
    print(f"  {'[DRY RUN] ' if dry_run else ''}Готово!")
    print(f"  Создано новых заказов: {created_count}")
    print(f"  Пропущено:             {len(skipped)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
