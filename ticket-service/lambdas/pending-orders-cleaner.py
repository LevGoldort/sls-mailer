"""
Lambda для очистки старых pending заказов
Запускается по расписанию (например, каждый час через EventBridge)
Удаляет заказы со статусом pending, которые старше 2 часов
"""
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.dynamodb import DynamoDBClient


def lambda_handler(event, context):
    """
    Очищает старые pending заказы

    Логика:
    - Находит все заказы со статусом 'pending'
    - Проверяет время создания (старше 2 часов)
    - Обновляет статус на 'expired' (или удаляет)
    - Билеты не нужно восстанавливать, т.к. они не резервировались при создании заказа
    """
    print("Starting pending orders cleanup...")

    db = DynamoDBClient()

    # Время отсечки: 2 часа назад
    cutoff_time = datetime.utcnow() - timedelta(hours=2)
    cutoff_timestamp = cutoff_time.isoformat()

    print(f"Cutoff time: {cutoff_timestamp}")

    try:
        # Получаем все заказы
        all_orders = db.list_orders(limit=1000)

        expired_count = 0

        for order in all_orders:
            payment_status = order.get('payment', {}).get('status')
            created_at = order.get('created_at', '')
            order_id = order.get('order_id')

            # Проверяем условия для очистки
            if payment_status == 'pending' and created_at < cutoff_timestamp:
                print(f"Expiring order {order_id} (created at {created_at})")

                # Обновляем статус на 'expired'
                db.update_order_payment_status(
                    order_id=order_id,
                    status='expired',
                    transaction_id=None
                )

                expired_count += 1

        print(f"Cleanup completed. Expired {expired_count} orders.")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Cleanup completed',
                'expired_count': expired_count
            })
        }

    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }


# For local testing
if __name__ == '__main__':
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))
