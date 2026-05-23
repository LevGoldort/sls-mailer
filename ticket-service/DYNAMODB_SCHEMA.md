# DynamoDB Schema Documentation

## Tables Overview

### Events Table
- **Name**: `yallabalagan-events-${Environment}`
- **Purpose**: Stores event data with ticket types and seat allocation
- **Key Schema**: PK (HASH), SK (RANGE)
- **GSIs**: GSI1, DateIndex, SlugIndex
- **New Fields for Seated Venues**:
  - `seat_allocation`: `Dict[str, str]` - Maps seat IDs to ticket type IDs
    - Example: `{"0-0": "tt-regular", "0-1": "tt-vip"}`

### Orders Table
- **Name**: `yallabalagan-orders-${Environment}`
- **Purpose**: Stores customer orders and ticket purchases
- **Key Schema**: PK (HASH), SK (RANGE)
- **GSIs**: EventIndex (event_id + created_at), EmailIndex (customer_email + created_at)
- **New Fields for Seated Venues**:
  - `purchased_seats`: `List[str]` - List of seat IDs purchased in this order
    - Example: `["0-0", "0-1"]`
  - Stored within each ticket in `tickets` array: `OrderTicket.purchased_seats`

### Seat Reservations Table
- **Name**: `yallabalagan-seat-reservations-${Environment}`
- **Purpose**: Temporary seat reservations during checkout process
- **Key Schema**: event_id (HASH), seat_id (RANGE)
- **GSI**: ExpirationIndex (event_id + expires_at)
- **TTL**: Enabled on `expires_at` attribute (UNIX timestamp)
- **Item Structure**:
  ```json
  {
    "event_id": "evt-123",
    "seat_id": "0-5",
    "session_id": "sess-abc",
    "ticket_type_id": "tt-regular",
    "expires_at": 1234567890,
    "reserved_at": "2025-12-09T10:00:00Z"
  }
  ```
- **TTL Behavior**: Items automatically deleted by DynamoDB ~48 hours after expiration
- **Reservation Duration**: Typically 10-15 minutes

## Naming Convention

Tables have no environment suffix — dev and prod are isolated via separate AWS accounts. All tables are named `yallabalagan-{table}` in both environments.

## Data Migration Notes

### Existing Events
Events created before seated venue support will have:
- `seat_allocation`: `null` or not present
- These are **standing venues** (general admission)

### Existing Orders
Orders created before seated venue support will have:
- `purchased_seats`: `[]` or not present
- These are orders for **standing venues**

**No migration required** - the code handles both cases correctly:
- If `seat_allocation` exists → seated venue
- If `seat_allocation` is null → standing venue

## Querying Examples

### Get all purchased seats for an event
```python
# Query Orders table using EventIndex GSI
orders = dynamodb.query(
    TableName='orders',
    IndexName='EventIndex',
    KeyConditionExpression='event_id = :event_id',
    FilterExpression='payment.status IN (completed, pending)'
)

purchased_seats = set()
for order in orders:
    for ticket in order['tickets']:
        purchased_seats.update(ticket.get('purchased_seats', []))
```

### Check if seat is reserved
```python
# Query SeatReservations table
response = dynamodb.get_item(
    TableName='seat-reservations',
    Key={
        'event_id': 'evt-123',
        'seat_id': '0-5'
    }
)

is_reserved = 'Item' in response
```

### Clean up expired reservations
```python
# Query using ExpirationIndex GSI
current_time = int(time.time())
expired = dynamodb.query(
    TableName='seat-reservations',
    IndexName='ExpirationIndex',
    KeyConditionExpression='event_id = :event_id AND expires_at < :now'
)

# Note: TTL will auto-delete these, but manual cleanup can be faster
```

## Performance Considerations

### Seat Allocation Storage
- Stored as JSON dict in Events table
- For large venues (1000+ seats), consider:
  - Compressing seat allocation data
  - Storing in S3 and referencing by URL
  - Current limit: ~400KB per item (sufficient for 10,000+ seats)

### Purchased Seats Query
- Orders.EventIndex GSI enables efficient queries by event
- For real-time seat availability, use:
  1. Query orders by event_id
  2. Filter by payment status (completed/pending)
  3. Aggregate purchased_seats

### Reservation Concurrency
- DynamoDB conditional writes prevent double-booking
- Use `ConditionExpression: attribute_not_exists(seat_id)`
- Handle `ConditionalCheckFailedException` = seat already reserved

## Backup & Recovery

### Automated Backups
- Point-in-time recovery (PITR): **Recommended to enable**
- On-demand backups: **Before major migrations**

### Critical Tables
1. **Orders** - Contains payment and ticket data (most critical)
2. **Events** - Seat allocations must match sold tickets
3. **SeatReservations** - Ephemeral, can be recreated

## Testing

### Local Development
```bash
# Use moto for DynamoDB mocking
pytest tests/test_seated_orders.py

# Tables created in conftest.py with test suffix
```

### Integration Tests
```bash
# Test TTL behavior (requires real DynamoDB)
# Create reservation with expires_at = now + 60 seconds
# Wait 2-3 minutes, verify auto-deletion
```

## Future Enhancements

### Considered Features
- [ ] Seat hold timeout notifications (SNS)
- [ ] Analytics on popular seat positions
- [ ] Dynamic pricing based on seat position
- [ ] Seat transfer between users
- [ ] Group seating recommendations
