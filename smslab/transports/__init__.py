"""
smslab.transports — Transport layer for SMSLab.

Only MockTransport is implemented. No real SMS can be sent from this package.
"""

from smslab.transports.base import DeliveryResult, Transport
from smslab.transports.mock import MockTransport

__all__ = ["DeliveryResult", "Transport", "MockTransport"]
