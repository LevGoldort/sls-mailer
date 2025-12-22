# Ticket Service Tests

Unit tests for the Yallabalagan ticket service seating system.

## Setup

Install test dependencies:

```bash
pip install -r requirements-test.txt
```

## Running Tests

Run all tests:
```bash
pytest tests/
```

Run specific test file:
```bash
pytest tests/test_seating_endpoints.py
pytest tests/test_reservation_endpoints.py
```

Run with coverage:
```bash
pytest tests/ --cov=lambdas --cov=utils --cov-report=html
```

Run with verbose output:
```bash
pytest tests/ -v
```

Run specific test:
```bash
pytest tests/test_seating_endpoints.py::test_get_seating_map_seated_venue -v
```

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                      # Pytest fixtures and mocks
├── test_seating_endpoints.py        # Tests for seating map & allocation endpoints
└── test_reservation_endpoints.py    # Tests for seat reservation endpoints
```

## Test Coverage

### Seating Endpoints (`test_seating_endpoints.py`)

- ✅ GET `/api/events/{event_id}/seating-map`
  - Seated venues
  - Standing venues
  - Event not found

- ✅ GET `/api/events/{event_id}/seat-availability`
  - Basic availability
  - With active reservations

- ✅ POST `/api/events/{event_id}/seat-allocation` (admin)
  - Valid allocation
  - Unauthorized access
  - Exceeds ticket type total
  - Cannot modify sold seats
  - Missing data

### Reservation Endpoints (`test_reservation_endpoints.py`)

- ✅ POST `/api/orders/reserve-seats`
  - Successful reservation
  - Already reserved (race condition)
  - Already purchased
  - Invalid seat
  - Missing fields
  - Empty seat list
  - Event not found
  - Concurrent reservation race condition

- ✅ POST `/api/orders/release-seats`
  - Successful release
  - Wrong session ID
  - Partial release
  - Missing fields

## Mocking

Tests use `moto` to mock AWS DynamoDB. All database operations are isolated and don't affect real AWS resources.

## Fixtures

Key fixtures in `conftest.py`:

- `db_client` - Mocked DynamoDB client
- `sample_event` - Test event with seat allocation
- `sample_location` - Test seated venue
- `admin_api_key` - Mock admin authentication
- `api_gateway_event` - Helper to create API Gateway events
