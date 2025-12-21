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
        customer_name: str = None,
        tickets: list = None,
        order_created_at: str = None
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
            tickets: Optional list of OrderTicket objects (for API mode)
            order_created_at: Optional ISO timestamp of order creation (for expire calculation)

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

    @abstractmethod
    def refund(
        self,
        order_id: str,
        amount: float,
        transaction_id: str = None
    ) -> Dict:
        """
        Issue a refund for a completed payment

        Args:
            order_id: Unique order identifier
            amount: Amount to refund
            transaction_id: Original transaction ID (optional)

        Returns:
            Dict with refund status and details

        Raises:
            Exception if refund fails
        """
        pass


class MockPaymentProvider(PaymentProvider):
    """Mock payment provider for development and testing"""

    def __init__(self):
        # Build base_url from FRONTEND_BUCKET if available, otherwise use BASE_URL
        frontend_bucket = os.environ.get('FRONTEND_BUCKET')
        if frontend_bucket:
            self.base_url = f'http://{frontend_bucket}.s3-website.eu-north-1.amazonaws.com'
        else:
            self.base_url = os.environ.get('BASE_URL', 'http://yallabalagan-tickets-frontend.s3-website.eu-north-1.amazonaws.com')
        self.webhook_url = os.environ.get('API_URL', 'https://ovajavet67.execute-api.eu-north-1.amazonaws.com')

    def create_payment_url(
        self,
        order_id: str,
        amount: float,
        currency: str,
        email: str,
        event_id: str = None,
        customer_name: str = None,
        tickets: list = None,
        order_created_at: str = None
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

        # Add expire parameter for testing (if order_created_at provided)
        if order_created_at:
            from datetime import datetime
            expire_minutes = int(os.environ.get('PAYMENT_EXPIRE_MINUTES', '10'))
            created_dt = datetime.fromisoformat(order_created_at.replace('Z', '+00:00'))
            expire = int(created_dt.timestamp()) + (expire_minutes * 60)
            params += f"&expire={expire}"

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

    def refund(
        self,
        order_id: str,
        amount: float,
        transaction_id: str = None
    ) -> Dict:
        """
        Mock refund - always succeeds for testing

        Returns:
            Dict with success status
        """
        print(f"[MOCK] Processing refund: order_id={order_id}, amount={amount}, transaction_id={transaction_id}")

        return {
            'success': True,
            'order_id': order_id,
            'refund_status': 'completed',
            'refunded_amount': amount,
            'message': 'Mock refund successful'
        }


class AllPayProvider(PaymentProvider):
    """Real All-Pay payment provider integration"""

    def __init__(self):
        # Legacy payment link URL
        self.api_url = os.environ.get('ALLPAY_API_URL', 'https://allpay.to/~yallabalagan/tickets-yallabalagan')

        # AllPay credentials
        self.login = os.environ.get('ALLPAY_LOGIN', '')
        self.webhook_secret = os.environ.get('ALLPAY_WEBHOOK_SECRET')
        if not self.webhook_secret:
            raise ValueError("ALLPAY_WEBHOOK_SECRET must be set for production mode")

        # API configuration
        self.api_key = os.environ.get('ALLPAY_API_KEY', '')
        self.use_api = os.environ.get('ALLPAY_USE_API', 'false').lower() == 'true'
        self.expire_minutes = int(os.environ.get('PAYMENT_EXPIRE_MINUTES', '10'))
        self.api_endpoint = 'https://allpay.to/app/?show=getpayment&mode=api9'

        # URLs
        api_url_base = os.environ.get('API_URL', 'https://wcyt1odrnc.execute-api.eu-north-1.amazonaws.com/dev')
        self.notifications_url = f"{api_url_base}/api/webhooks/allpay"

        frontend_bucket = os.environ.get('FRONTEND_BUCKET', 'yallabalagan-tickets-frontend-dev')
        self.frontend_url = f"http://{frontend_bucket}.s3-website.eu-north-1.amazonaws.com"

        # Return URL after payment (for legacy links)
        self.return_url = os.environ.get('PAYMENT_RETURN_URL', f'{self.frontend_url}/processing.html')

    def _generate_request_signature(self, params: Dict) -> str:
        """
        Generate AllPay API request signature.

        Algorithm (from AllPay documentation):
        1. Remove 'sign' field from params
        2. Sort keys alphabetically
        3. Concatenate non-empty string values with colons
        4. Append API key
        5. SHA256 hex digest

        Args:
            params: Request parameters dict

        Returns:
            SHA256 hex signature
        """
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

        # Build base string: value1:value2:value3:...:api_key
        base_string = ':'.join(chunks) + ':' + self.api_key

        # Calculate SHA256 hash
        signature = hashlib.sha256(base_string.encode('utf-8')).hexdigest()

        print(f"Generated signature from {len(chunks)} values")
        return signature

    def _create_payment_via_api(
        self,
        order_id: str,
        amount: float,
        currency: str,
        email: str,
        customer_name: str,
        tickets: list,
        expire_timestamp: int
    ) -> str:
        """
        Create payment via AllPay API v9.

        Args:
            order_id: Unique order identifier
            amount: Total amount to charge
            currency: Currency code
            email: Customer email
            customer_name: Customer name
            tickets: List of OrderTicket objects
            expire_timestamp: Unix timestamp for payment expiration

        Returns:
            payment_url from API response

        Raises:
            Exception if API call fails
        """
        import requests

        # Build items array from tickets
        items = []
        for ticket in tickets:
            items.append({
                "name": ticket.type_name,
                "qty": ticket.quantity,  # AllPay API requires "qty" field as integer
                "price": f"{ticket.price_per_ticket:.2f}",
                "vat": "Y"  # All prices include VAT in Israel
            })

        # Build request body
        request_body = {
            "login": self.login,
            "order_id": order_id,
            "items": items,
            "currency": "ILS",
            "notifications_url": self.notifications_url,
            "client_email": email,
            # Note: client_phone omitted (not collected currently, avoid empty strings)
            "expire": expire_timestamp,
            "lang": "EN"  # Payment form language
            # Note: success_url and backlink_url removed - S3 URLs cause "Invalid domain" error
            # AllPay will use their default success page. User will be notified via webhook.
        }

        # Only include client_name if provided (AllPay requires non-empty name)
        if customer_name and customer_name.strip():
            request_body["client_name"] = customer_name.strip()

        # Generate signature
        signature = self._generate_request_signature(request_body)
        request_body['sign'] = signature

        print(f"Creating AllPay API payment for order {order_id}, expires at {expire_timestamp}")
        print(f"Items: {len(items)} ticket types, total amount: {amount} {currency}")
        print(f"AllPay request body: {json.dumps(request_body, ensure_ascii=False)}")

        try:
            response = requests.post(
                self.api_endpoint,
                json=request_body,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            # AllPay API returns: {payment_url: "https://allpay.to/payment/abc123"}
            payment_url = result.get('payment_url')
            if not payment_url:
                raise Exception(f"AllPay API response missing payment_url: {result}")

            print(f"AllPay API payment created successfully: {payment_url}")
            return payment_url

        except requests.RequestException as e:
            print(f"AllPay API request failed: {str(e)}")
            raise Exception(f"Failed to create payment via API: {str(e)}")

    def create_payment_url(
        self,
        order_id: str,
        amount: float,
        currency: str,
        email: str,
        event_id: str = None,
        customer_name: str = None,
        tickets: list = None,
        order_created_at: str = None
    ) -> str:
        """
        Create payment URL for AllPay redirect

        Supports two modes:
        1. API mode (use_api=true): POST to AllPay API, get payment_url with expire support
        2. Legacy mode (use_api=false): Direct URL construction with query parameters
        """
        # Feature flag check: Use API if enabled and credentials available
        if self.use_api and self.login and self.api_key:
            # Validate required parameters for API mode
            if not tickets:
                raise ValueError("tickets parameter required for API-based payments")

            # Calculate expire timestamp: created_at + PAYMENT_EXPIRE_MINUTES
            from datetime import datetime
            if order_created_at:
                created_dt = datetime.fromisoformat(order_created_at.replace('Z', '+00:00'))
            else:
                created_dt = datetime.utcnow()

            expire_seconds = self.expire_minutes * 60
            expire_timestamp = int(created_dt.timestamp()) + expire_seconds

            # Call API method
            return self._create_payment_via_api(
                order_id=order_id,
                amount=amount,
                currency=currency,
                email=email,
                customer_name=customer_name,
                tickets=tickets,
                expire_timestamp=expire_timestamp
            )

        # Fallback to legacy payment link
        from urllib.parse import urlencode

        print(f"Using legacy payment link mode (use_api={self.use_api}, login={bool(self.login)}, api_key={bool(self.api_key)})")

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

                # Handle arrays (e.g., items field) - only for requests, not webhooks
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
                    # For webhooks, AllPay sends items as JSON string - use as-is
                    chunks.append(str(value).strip())

            # Build base string: value1:value2:value3:...:api_key
            # NOTE: AllPay uses API key for webhook signatures, not webhook secret
            secret_to_use = self.api_key if self.api_key else self.webhook_secret
            base_string = ':'.join(chunks) + ':' + secret_to_use

            print(f"[WEBHOOK VERIFY] Sorted keys: {sorted_keys}")
            print(f"[WEBHOOK VERIFY] Values: {chunks}")
            print(f"[WEBHOOK VERIFY] Using secret type: {'API_KEY' if self.api_key else 'WEBHOOK_SECRET'}")
            print(f"[WEBHOOK VERIFY] Base string length: {len(base_string)}")

            # Calculate SHA256 hash
            calculated_signature = hashlib.sha256(base_string.encode('utf-8')).hexdigest()

            print(f"[WEBHOOK VERIFY] Calculated signature: {calculated_signature}")
            print(f"[WEBHOOK VERIFY] Received signature: {request_signature}")

            # Compare signatures
            is_valid = hmac.compare_digest(calculated_signature, request_signature)

            if not is_valid:
                print(f"[WEBHOOK VERIFY] Signature verification FAILED")
            else:
                print(f"[WEBHOOK VERIFY] Signature verification PASSED")

            return is_valid

        except Exception as e:
            print(f"Error verifying AllPay signature: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def refund(
        self,
        order_id: str,
        amount: float,
        transaction_id: str = None
    ) -> Dict:
        """
        Issue refund via AllPay API

        API Endpoint: POST https://allpay.to/app/?show=refund&mode=api9
        Required: login, order_id, amount, sign (SHA256)

        Args:
            order_id: Our internal order identifier
            amount: Amount to refund (in ILS, e.g., 100.50)
            transaction_id: AllPay receipt/transaction ID (optional)

        Returns:
            Dict with refund status

        Raises:
            Exception if refund fails
        """
        import requests

        # Get AllPay credentials from environment
        allpay_login = os.environ.get('ALLPAY_LOGIN')
        if not allpay_login:
            raise ValueError("ALLPAY_LOGIN must be set for refunds")

        # Build refund request
        refund_data = {
            'login': allpay_login,
            'order_id': order_id,
            'amount': f"{amount:.2f}"  # Format as decimal string
        }

        # Calculate signature: SHA256(login:order_id:amount:secret)
        sign_string = f"{allpay_login}:{order_id}:{refund_data['amount']}:{self.webhook_secret}"
        signature = hashlib.sha256(sign_string.encode('utf-8')).hexdigest()
        refund_data['sign'] = signature

        # Make API request
        refund_url = 'https://allpay.to/app/?show=refund&mode=api9'

        print(f"Requesting refund from AllPay: order_id={order_id}, amount={amount}")

        try:
            response = requests.post(
                refund_url,
                json=refund_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            # AllPay returns: {order_id, status: 3 (full refund) or 4 (partial)}
            if result.get('status') in [3, 4]:
                print(f"Refund successful: {result}")
                return {
                    'success': True,
                    'order_id': order_id,
                    'refund_status': 'completed',
                    'refunded_amount': amount,
                    'allpay_response': result
                }
            else:
                raise Exception(f"AllPay refund failed with status: {result.get('status')}")

        except requests.RequestException as e:
            print(f"AllPay refund request failed: {str(e)}")
            raise Exception(f"Failed to process refund: {str(e)}")


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
    Parse and validate webhook payload from AllPay or Mock payment provider

    AllPay Webhook Fields:
    - status: 1 = success, other = failure
    - add_field: custom data (contains our order_id)
    - receipt: AllPay transaction ID
    - client_name, client_email, client_phone
    - card_mask, card_brand, foreign_card
    - sign: HMAC signature

    Mock Webhook Fields:
    - order_id: order identifier
    - status: 'completed' or 'failed'
    - transaction_id: mock transaction ID
    - amount, currency, timestamp

    Args:
        body: Raw webhook body (JSON string)

    Returns:
        Normalized dict with ticket-service expected fields

    Raises:
        ValueError: If payload is invalid
    """
    try:
        data = json.loads(body)

        # Check if this is a Mock webhook (has 'order_id' field directly)
        if 'order_id' in data:
            # Mock webhook format
            if 'status' not in data:
                raise ValueError("Missing 'status' field in Mock webhook")

            normalized = {
                'order_id': data['order_id'],
                'status': data['status'],  # 'completed' or 'failed'
                'transaction_id': data.get('transaction_id', ''),
            }

            return normalized

        # AllPay webhook format
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
