"""
SMSLab — Mock-first SMS/OTP integration testing CLI.

No real SMS is ever sent by this package. The only working transport is MockTransport.
This is enforced at config load time (transport != "mock" → ConfigError) and structurally
(no network code anywhere in this package).
"""

__version__ = "1.0.0"
__author__ = "Harsh Zagade"
