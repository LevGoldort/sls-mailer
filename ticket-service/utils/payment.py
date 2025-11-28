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
        event_id: str = None
    ) -> str:
        """
        Create payment URL for order

        Args:
            order_id: Unique order identifier
            amount: Total amount to charge
            currency: Currency code (e.g., 'ILS')
            email: Customer email
            event_id: Optional event ID for metadata

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
        event_id: str = None
    ) -> str:
        """
        Returns URL to mock payment page
        Mock page will auto-complete payment after 3 seconds
        """
        # URL encode parameters for mock payment page
        params = f"order_id={order_id}&amount={amount}&currency={currency}&email={email}"
        if event_id:
            params += f"&event_id={event_id}"

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
        self.api_url = os.environ.get('ALLPAY_API_URL', 'https://api.allpay.co.il')
        self.api_key = os.environ.get('ALLPAY_API_KEY')
        self.webhook_secret = os.environ.get('ALLPAY_WEBHOOK_SECRET')
        self.return_url = os.environ.get('PAYMENT_RETURN_URL',
                                        'http://yallabalagan-tickets-frontend.s3-website.eu-north-1.amazonaws.com/processing.html')

        if not self.api_key or not self.webhook_secret:
            raise ValueError("ALLPAY_API_KEY and ALLPAY_WEBHOOK_SECRET must be set for production mode")

    def create_payment_url(
        self,
        order_id: str,
        amount: float,
        currency: str,
        email: str,
        event_id: str = None
    ) -> str:
        """
        Create payment URL via All-Pay API

        This is a placeholder implementation - adjust based on actual All-Pay API docs
        """
        import requests

        # Prepare payment request
        payment_data = {
            'amount': amount,
            'currency': currency,
            'order_id': order_id,
            'customer_email': email,
            'return_url': f"{self.return_url}?order_id={order_id}",
            'webhook_url': f"{os.environ.get('API_URL')}/api/webhooks/allpay",
            'metadata': {
                'event_id': event_id
            } if event_id else {}
        }

        # Make API request to All-Pay
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(
                f"{self.api_url}/v1/payments",
                json=payment_data,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            result = response.json()
            return result.get('payment_url') or result.get('checkout_url')

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to create All-Pay payment: {str(e)}")

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify All-Pay webhook signature using HMAC-SHA256

        Args:
            payload: Raw request body
            signature: Signature from X-AllPay-Signature header (or similar)

        Returns:
            True if signature is valid
        """
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected_signature)


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
    Parse and validate webhook payload

    Args:
        body: Raw webhook body (JSON string)

    Returns:
        Parsed webhook data

    Raises:
        ValueError: If payload is invalid
    """
    try:
        data = json.loads(body)

        # Validate required fields
        required_fields = ['order_id', 'status']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        return data

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON payload: {str(e)}")
