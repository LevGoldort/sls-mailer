"""
Миграция из зала без мест в зал с местами.

Что делает:
  1. Читает migration_plan_ashkelon.csv (сгенерирован заранее)
  2. Для каждого старого заказа создаёт НОВЫЙ заказ в новом эвенте:
     - Новый order_id, новый event_id
     - Те же данные покупателя и оплаты
     - Назначает новые места (purchased_seats, qr_codes[].seat_id)
     - Пропускает отменённые QR-коды
  3. Обновляет available в ticket_types нового эвента
  4. Идемпотентность через migrated_from_order_id

Что НЕ делает:
  - Не трогает старые заказы
  - Не отправляет уведомления

Запуск:
  python3 scripts/migrate_unseated_to_seated.py [--dry-run]
"""

import argparse
import csv
import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

import boto3

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

OLD_EVENT_ID = "a6003898-bc0e-4a92-86f1-4efe214e5b7e"
NEW_EVENT_ID = "51759c7c-dfeb-474d-8159-a3cabfc6c993"
NEW_TYPE_ID   = "tt-1773949094548-0"   # Первые ряды
NEW_TYPE_NAME = "Первые ряды"

PLAN_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migration_plan_ashkelon.csv")
LOG_PATH  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migration_log_ashkelon.json")

REGION       = "eu-north-1"
ORDERS_TABLE = os.environ.get("ORDERS_TABLE", "yallabalagan-orders")
EVENTS_TABLE = os.environ.get("EVENTS_TABLE", "yallabalagan-events")


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def dynamodb_resource():
    return boto3.resource("dynamodb", region_name=REGION)


def get_order(table, order_id):
    resp = table.get_item(Key={"PK": f"ORDER#{order_id}", "SK": "METADATA"})
    return resp.get("Item")


def get_event(table, event_id):
    resp = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"})
    return resp.get("Item")


def check_already_migrated(orders_table, old_order_id):
    from boto3.dynamodb.conditions import Key, Attr
    resp = orders_table.query(
        IndexName="EventIndex",
        KeyConditionExpression=Key("event_id").eq(NEW_EVENT_ID),
        FilterExpression=Attr("migrated_from_order_id").eq(old_order_id),
    )
    return len(resp.get("Items", [])) > 0


def load_plan(path):
    """Returns {order_id: [grid_key, ...]} — ordered list of new seats per order."""
    plan = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            plan[row["Order ID"]].append(row["Новый grid_key"])
    return plan


def build_new_order(old_order, new_seats, new_order_id):
    """
    old_order:  DynamoDB item старого заказа
    new_seats:  список новых grid_key (только для активных QR)
    """
    now = datetime.now(timezone.utc).isoformat()

    # Active QRs — в том же порядке, получают seats по индексу
    active_qrs = [qr for qr in old_order.get("qr_codes", []) if qr.get("cancelled") != True]

    if len(active_qrs) != len(new_seats):
        raise ValueError(
            f"Order {old_order['order_id'][:8]}: "
            f"active QRs={len(active_qrs)} but plan seats={len(new_seats)}"
        )

    # Обновляем seat_id в каждом активном QR
    new_qr_codes = []
    for qr, seat in zip(active_qrs, new_seats):
        new_qr_codes.append({**qr, "seat_id": seat})

    # Обновляем tickets: тип меняем на Первые ряды, ставим purchased_seats
    # Старый билет один (Место на стуле), qty = len(new_seats)
    new_tickets = []
    for ticket in old_order.get("tickets", []):
        new_tickets.append({
            **ticket,
            "type_id":    NEW_TYPE_ID,
            "type_name":  NEW_TYPE_NAME,
            "purchased_seats": new_seats,
        })

    new_item = {
        "PK":             f"ORDER#{new_order_id}",
        "SK":             "METADATA",
        "order_id":       new_order_id,
        "event_id":       NEW_EVENT_ID,
        "customer":       old_order["customer"],
        "customer_email": old_order.get("customer_email", old_order["customer"].get("email", "")),
        "tickets":        new_tickets,
        "total_amount":   old_order["total_amount"],
        "currency":       old_order.get("currency", "ILS"),
        "payment":        old_order["payment"],
        "qr_codes":       new_qr_codes,
        "notifications":  {"email_sent": False, "sms_sent": False, "reminder_sent": False},
        "created_at":     now,
        "migrated_from_order_id": old_order["order_id"],
        "migrated_from_event_id": old_order["event_id"],
        "migrated_at":    now,
    }

    if old_order.get("coupon_code"):
        new_item["coupon_code"] = old_order["coupon_code"]
    if old_order.get("discount_amount"):
        new_item["discount_amount"] = old_order["discount_amount"]

    return new_item


def update_event_available(events_table, total_seats, dry_run):
    event = get_event(events_table, NEW_EVENT_ID)
    if not event:
        raise RuntimeError(f"New event {NEW_EVENT_ID} not found!")

    ticket_types = event.get("ticket_types", [])
    updated = False
    for tt in ticket_types:
        tid = tt.get("id") or tt.get("type_id")
        if tid == NEW_TYPE_ID:
            old_avail = int(tt["available"])
            new_avail = old_avail - total_seats
            if new_avail < 0:
                raise ValueError(f"Не хватает мест! available={old_avail} need={total_seats}")
            print(f"  {tt['name']}: available {old_avail} → {new_avail}")
            tt["available"] = Decimal(str(new_avail))
            updated = True

    if not updated:
        print("  ⚠️  type_id не найден, available не обновлён!")
        return

    if dry_run:
        print("  [DRY RUN] Обновление available пропущено")
        return

    events_table.put_item(Item={**event, "ticket_types": ticket_types,
                                "updated_at": datetime.now(timezone.utc).isoformat()})
    print("  ✓ available обновлён")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    if dry_run:
        print("=" * 60)
        print("  DRY RUN — никаких изменений в DynamoDB не будет")
        print("=" * 60)

    db = dynamodb_resource()
    orders_table = db.Table(ORDERS_TABLE)
    events_table = db.Table(EVENTS_TABLE)

    print(f"\n📋 Читаем план: {PLAN_PATH}")
    plan = load_plan(PLAN_PATH)
    print(f"   Уникальных заказов в плане: {len(plan)}")

    print(f"\n📥 Загружаем старые заказы из DynamoDB...")
    old_orders = {}
    for order_id in plan:
        item = get_order(orders_table, order_id)
        if not item:
            print(f"  ⚠️  {order_id[:8]} не найден, пропускаем")
        else:
            old_orders[order_id] = item
    print(f"   Найдено: {len(old_orders)}")

    log_entries = []
    skipped = []
    created_count = 0
    total_seats_migrated = 0

    print(f"\n🚀 Создаём новые заказы...")

    for order_id, new_seats in plan.items():
        old_order = old_orders.get(order_id)
        if not old_order:
            skipped.append({"order_id": order_id, "reason": "not found in DB"})
            continue

        if check_already_migrated(orders_table, order_id):
            print(f"  ⏭  {order_id[:8]} уже мигрирован, пропускаем")
            skipped.append({"order_id": order_id, "reason": "already migrated"})
            continue

        new_order_id = str(uuid.uuid4())

        try:
            new_item = build_new_order(old_order, new_seats, new_order_id)
        except ValueError as e:
            print(f"  ❌ {order_id[:8]}: {e}")
            skipped.append({"order_id": order_id, "reason": str(e)})
            continue

        customer_name = old_order.get("customer", {}).get("name", "?")

        if dry_run:
            print(f"  [DRY] {order_id[:8]} → {new_order_id[:8]}  {customer_name[:22]}  seats→{new_seats}")
        else:
            orders_table.put_item(Item=new_item)
            print(f"  ✓ {order_id[:8]} → {new_order_id[:8]}  {customer_name[:22]}")

        log_entries.append({
            "old_order_id": order_id,
            "new_order_id": new_order_id,
            "customer":     customer_name,
            "new_seats":    new_seats,
        })
        created_count += 1
        total_seats_migrated += len(new_seats)

    print(f"\n📊 Обновляем available в новом эвенте ({NEW_EVENT_ID[:8]}...):")
    update_event_available(events_table, total_seats_migrated, dry_run)

    log = {
        "run_at":       datetime.now(timezone.utc).isoformat(),
        "dry_run":      dry_run,
        "created":      created_count,
        "seats":        total_seats_migrated,
        "skipped":      len(skipped),
        "skipped_list": skipped,
        "entries":      log_entries,
    }
    if not dry_run:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2, cls=DecimalEncoder)
        print(f"\n📝 Лог сохранён: {LOG_PATH}")

    print(f"\n{'=' * 60}")
    print(f"  {'[DRY RUN] ' if dry_run else ''}Готово!")
    print(f"  Создано заказов:  {created_count}")
    print(f"  Мигрировано мест: {total_seats_migrated}")
    print(f"  Пропущено:        {len(skipped)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
