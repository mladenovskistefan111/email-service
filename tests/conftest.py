"""
Shared pytest fixtures for the email-service test suite.

All fixtures are auto-discovered by pytest — no imports needed in test files.
We use plain Python objects instead of generated protobuf stubs so the unit
tests can run without a grpc compilation step.
"""

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Lightweight proto message stand-ins
# ---------------------------------------------------------------------------


class _Money:
    def __init__(self, currency_code="USD", units=10, nanos=990000000):
        self.currency_code = currency_code
        self.units = units
        self.nanos = nanos


class _Address:
    def __init__(
        self,
        street_address="123 Main St",
        city="New York",
        state="NY",
        country="US",
        zip_code=10001,
    ):
        self.street_address = street_address
        self.city = city
        self.state = state
        self.country = country
        self.zip_code = zip_code


class _CartItem:
    def __init__(self, product_id="PROD-001", quantity=2):
        self.product_id = product_id
        self.quantity = quantity


class _OrderItem:
    def __init__(self, product_id="PROD-001", quantity=2, cost=None):
        self.item = _CartItem(product_id=product_id, quantity=quantity)
        self.cost = cost or _Money()


class _OrderResult:
    def __init__(
        self,
        order_id="ORD-123",
        shipping_tracking_id="TRACK-456",
        shipping_cost=None,
        shipping_address=None,
        items=None,
    ):
        self.order_id = order_id
        self.shipping_tracking_id = shipping_tracking_id
        self.shipping_cost = shipping_cost or _Money(units=5, nanos=990000000)
        self.shipping_address = shipping_address or _Address()
        self.items = items if items is not None else [_OrderItem()]


class _SendOrderConfirmationRequest:
    def __init__(self, email="customer@example.com", order=None):
        self.email = email
        self.order = order or _OrderResult()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_request():
    """Well-formed SendOrderConfirmationRequest with a single order item."""
    return _SendOrderConfirmationRequest()


@pytest.fixture()
def multi_item_request():
    """Request carrying multiple order items."""
    items = [
        _OrderItem(
            product_id="PROD-001", quantity=1, cost=_Money(units=9, nanos=990000000)
        ),
        _OrderItem(
            product_id="PROD-002", quantity=3, cost=_Money(units=24, nanos=970000000)
        ),
    ]
    order = _OrderResult(order_id="ORD-999", items=items)
    return _SendOrderConfirmationRequest(email="bulk@example.com", order=order)


@pytest.fixture()
def empty_items_request():
    """Request whose order contains no line items."""
    return _SendOrderConfirmationRequest(order=_OrderResult(items=[]))


@pytest.fixture()
def mock_grpc_context():
    """Minimal mock of a gRPC ServicerContext."""
    ctx = MagicMock()
    ctx.set_code = MagicMock()
    ctx.set_details = MagicMock()
    return ctx


# Expose the builder classes as fixtures so tests can construct custom objects.
@pytest.fixture()
def make_money():
    return _Money


@pytest.fixture()
def make_address():
    return _Address


@pytest.fixture()
def make_order():
    return _OrderResult


@pytest.fixture()
def make_request():
    return _SendOrderConfirmationRequest
