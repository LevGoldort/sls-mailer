"""
Удаляет все мигрированные заказы из нового эвента и сбрасывает available.
Запускать ТОЛЬКО если миграция прошла с багом.

После этого скрипта — запускать migrate_event.py заново.
"""
import boto3
import sys
from decimal import Decimal
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

NEW_EVENT_ID = "196ff109-c2aa-417d-8aec-5a0f3fa09731"
REGION = "eu-north-1"
ORDERS_TABLE = "yallabalagan-orders"
EVENTS_TABLE = "yallabalagan-events"

# Оригинальные значения available ДО миграции
ORIGINAL_AVAILABLE = {
    "tt-1773932968713-0": 106,  # Первые ряды
    "tt-1773933120342-1": 201,  # Середина зала
    "tt-1773933141028-2": 86,   # Задние ряды
}

dry_run = "--dry-run" in sys.argv

if dry_run:
    print("=" * 60)
    print("  DRY RUN")
    print("=" * 60)

db = boto3.resource("dynamodb", region_name=REGION)
orders_t = db.Table(ORDERS_TABLE)
events_t = db.Table(EVENTS_TABLE)

# Получаем все заказы нового эвента с полем migrated_from_order_id
print(f"\nЗагружаем мигрированные заказы из нового эвента...")
resp = orders_t.query(
    IndexName="EventIndex",
    KeyConditionExpression=Key("event_id").eq(NEW_EVENT_ID),
)
all_orders = resp["Items"]
while resp.get("LastEvaluatedKey"):
    resp = orders_t.query(
        IndexName="EventIndex",
        KeyConditionExpression=Key("event_id").eq(NEW_EVENT_ID),
        ExclusiveStartKey=resp["LastEvaluatedKey"]
    )
    all_orders += resp["Items"]

migrated = all_orders
print(f"  Найдено заказов: {len(migrated)}")

if not migrated:
    print("  Нечего удалять.")
else:
    print(f"\nУдаляем {len(migrated)} заказов...")
    for order in migrated:
        oid = order["order_id"]
        if dry_run:
            print(f"  [DRY] DELETE ORDER#{oid[:8]}  (from {order.get('migrated_from_order_id','')[:8]})")
        else:
            orders_t.delete_item(Key={"PK": f"ORDER#{oid}", "SK": "METADATA"})
            print(f"  ✓ Удалён ORDER#{oid[:8]}")

# Сбрасываем available
print(f"\nСбрасываем available в новом эвенте...")
ev = events_t.get_item(Key={"PK": f"EVENT#{NEW_EVENT_ID}", "SK": "METADATA"})["Item"]
ticket_types = ev.get("ticket_types", [])
for tt in ticket_types:
    tid = tt.get("id") or tt.get("type_id")
    if tid in ORIGINAL_AVAILABLE:
        old_val = int(tt["available"])
        new_val = ORIGINAL_AVAILABLE[tid]
        print(f"  {tt['name']}: {old_val} → {new_val}")
        tt["available"] = Decimal(str(new_val))

if dry_run:
    print("  [DRY RUN] Обновление available пропущено")
else:
    events_t.put_item(Item={**ev, "ticket_types": ticket_types,
                            "updated_at": datetime.now(timezone.utc).isoformat()})
    print("  ✓ available сброшен")

print(f"\n{'[DRY RUN] ' if dry_run else ''}Готово. Теперь запускай: python3 scripts/migrate_event.py")
