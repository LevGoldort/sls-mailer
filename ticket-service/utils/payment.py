"""Payment provider abstraction for All-Pay integration"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
import os
import hmac
import hashlib
import json


class PaymentProvider(ABC):
    """Abstract base class for payment providers"""

    @abstractmethod
    def create_payment_url(
        self,
        order_id: str,
        amount: float,
        currency: str,
        email: str,
        event_id: str = None,
        customer_name: str = None
    ) -> str:
        """
        Create payment URL for order

        Args:
            order_id: Unique order identifier
            amount: Total amount to charge
            currency: Currency code (e.g., 'ILS')
            email: Customer email
            event_id: Optional event ID for metadata
            customer_name: Optional customer name

        Returns:
            URL to redirect user for payment
        """
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify webhook signature from payment provider

        Args:
            payload: Raw request body
            signature: Signature from webhook headers

        Returns:
            True if signature is valid
        """
        pass


class MockPaymentProvider(PaymentProvider):
    """Mock payment provider for development and testing"""

    def __init__(self):
        self.base_url = os.environ.get('BASE_URL', 'http://yallabalagan-tickets-frontend.s3-website.eu-north-1.amazonaws.com')
        self.webhook_url = os.environ.get('API_URL', 'https://ovajavet67.execute-api.eu-north-1.amazonaws.com')

    def create_payment_url(
        self,
        order_id: str,
        amount: float,
        currency: str,
        email: str,
        event_id: str = None,
        customer_name: str = None
    ) -> str:
        """
        Returns URL to mock payment page
        Mock page will auto-complete payment after 3 seconds
        """
        # URL encode parameters for mock payment page
        params = f"order_id={order_id}&amount={amount}&currency={currency}&email={email}"
        if event_id:
            params += f"&event_id={event_id}"
        if customer_name:
            params += f"&customer_name={customer_name}"

        return f"{self.base_url}/mock_payment.html?{params}"

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Mock signature verification
        In mock mode, we accept any non-empty signature for testing
        This is safe because mock mode is only for development
        """
        # For mock mode, accept any signature (HTTP doesn't support crypto.subtle)
        # Just verify it's not empty to ensure the header was sent
        print(f"[MOCK] Verifying signature: signature='{signature}', len={len(signature) if signature else 0}")
        result = bool(signature and len(signature) > 0)
        print(f"[MOCK] Signature verification result: {result}")
        return result


class AllPayProvider(PaymentProvider):
    """Real All-Pay payment provider integration"""

    def __init__(self):
        self.api_url = os.environ.get('ALLPAY_API_URL', 'https://allpay.to/~yallabalagan/tickets-yallabalagan')
        self.webhook_secret = os.environ.get('ALLPAY_WEBHOOK_SECRET')
        self.return_url = os.environ.get('PAYMENT_RETURN_URL',
                                        'http://yallabalagan-tickets-frontend.s3-website.eu-north-1.amazonaws.com/processing.html')

        if not self.webhook_secret:
            raise ValueError("ALLPAY_WEBHOOK_SECRET must be set for production mode")

    def create_payment_url(
        self,
        order_id: str,
        amount: float,
        currency: str,
        email: str,
        event_id: str = None,
        customer_name: str = None
    ) -> str:
        """
        Create payment URL for AllPay redirect

        AllPay uses URL-based payment pages, not REST API.
        Format: https://allpay.to/~yallabalagan/tickets?amount=100&client_email=...&client_name=...&add_field=ORDER123
        """
        from urllib.parse import urlencode

        # Construct add_field parameter to pass order_id back in webhook
        add_field = order_id

        # Build AllPay payment URL with query parameters
        params = {
            'amount': int(amount),  # AllPay expects integer (agorot for ILS)
            'client_email': email,
            'add_field': add_field
        }

        # Add client_name if provided
        if customer_name:
            params['client_name'] = customer_name

        query_string = urlencode(params)
        allpay_url = f"{self.api_url}?{query_string}"

        print(f"Generated AllPay URL for order {order_id}: {allpay_url}")
        return allpay_url

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify AllPay webhook signature using their specific algorithm

        AllPay Algorithm:
        1. Parse JSON body to dict
        2. Remove 'sign' field
        3. Filter out empty values
        4. Sort keys alphabetically
        5. For each key, append value (handle nested arrays/objects)
        6. Join with colons, append secret, SHA256 hash

        Args:
            payload: Raw JSON request body
            signature: Signature from 'sign' field in JSON body (NOT header)

        Returns:
            True if signature is valid
        """
        try:
            # Parse payload to dict
            params = json.loads(payload.decode('utf-8'))

            # Extract signature from body (AllPay puts it in 'sign' field)
            request_signature = params.get('sign')
            if not request_signature:
                print("ERROR: Missing 'sign' field in AllPay webhook")
                return False

            # Create copy without 'sign' field
            params_copy = {k: v for k, v in params.items() if k != 'sign'}

            # Filter empty values and sort keys
            sorted_keys = sorted([
                k for k in params_copy.keys()
                if params_copy[k] is not None and str(params_copy[k]).strip() != ''
            ])

            # Build signature string according to AllPay algorithm
            chunks = []
            for key in sorted_keys:
                value = params_copy[key]

                # Handle arrays (e.g., items field)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            # Sort nested object keys and add values
                            for sub_key in sorted(item.keys()):
                                val = item[sub_key]
                                if val is not None and str(val).strip() != '':
                                    chunks.append(str(val).strip())
                        else:
                            chunks.append(str(item).strip())
                else:
                    chunks.append(str(value).strip())

            # Build base string: value1:value2:value3:...:secret
            base_string = ':'.join(chunks) + ':' + self.webhook_secret

            # Calculate SHA256 hash
            calculated_signature = hashlib.sha256(base_string.encode('utf-8')).hexdigest()

            # Compare signatures
            is_valid = hmac.compare_digest(calculated_signature, request_signature)

            if not is_valid:
                print(f"Signature verification FAILED")
                print(f"Calculated: {calculated_signature}")
                print(f"Received: {request_signature}")

            return is_valid

        except Exception as e:
            print(f"Error verifying AllPay signature: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


def get_payment_provider() -> PaymentProvider:
    """
    Factory function to get appropriate payment provider based on environment

    Returns:
        PaymentProvider instance (Mock or AllPay)
    """
    payment_mode = os.environ.get('PAYMENT_MODE', 'mock').lower()

    if payment_mode == 'production':
        return AllPayProvider()
    else:
        return MockPaymentProvider()


# Helper function for webhook processing
def parse_webhook_payload(body: str) -> Dict:
    """
    Parse and validate AllPay webhook payload

    AllPay Webhook Fields:
    - status: 1 = success, other = failure
    - add_field: custom data (contains our order_id)
    - receipt: AllPay transaction ID
    - client_name, client_email, client_phone
    - card_mask, card_brand, foreign_card
    - sign: HMAC signature

    Args:
        body: Raw webhook body (JSON string)

    Returns:
        Normalized dict with ticket-service expected fields

    Raises:
        ValueError: If payload is invalid
    """
    try:
        data = json.loads(body)

        # Validate AllPay required fields
        if 'status' not in data:
            raise ValueError("Missing 'status' field in AllPay webhook")

        if 'add_field' not in data:
            raise ValueError("Missing 'add_field' field - order_id not passed")

        # Map AllPay fields to ticket-service expected format
        normalized = {
            'order_id': data['add_field'],  # We pass order_id via add_field
            'status': 'completed' if data['status'] == 1 else 'failed',
            'transaction_id': data.get('receipt', ''),

            # AllPay metadata (for logging)
            'amount': data.get('amount', 0),
            'client_name': data.get('client_name', ''),
            'client_email': data.get('client_email', ''),
            'card_mask': data.get('card_mask', ''),
            'card_brand': data.get('card_brand', ''),
        }

        return normalized

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON payload: {str(e)}")
