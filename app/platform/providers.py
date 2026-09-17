"""Provider ports. Sandbox implementations are explicit, deterministic test doubles.

Live adapters must verify callbacks and normalize settlement/return semantics into
these ports. Provider selection is intentionally not inferred from demo currency.
"""
from typing import Protocol
from dataclasses import dataclass

@dataclass(frozen=True)
class PaymentResult:
    status: str
    reference: str
    detail: str = ''

class PaymentProvider(Protocol):
    def execute(self, *, key: str, amount_minor: int, currency: str, kind: str, bank_token: str) -> PaymentResult: ...

class IdentityProvider(Protocol):
    def submit(self, *, key: str, identity: dict, document: bytes, selfie: bytes) -> dict: ...

class NotificationProvider(Protocol):
    def send(self, *, key: str, channel: str, destination: str, title: str, body: str) -> str: ...

class SandboxPayments:
    def execute(self, *, key, amount_minor, currency, kind, bank_token):
        if bank_token.startswith('sandbox-fail-'):
            return PaymentResult('Failed','sandbox:'+key,'Sandbox insufficient-funds scenario')
        if bank_token.startswith('sandbox-pending-'):
            return PaymentResult('Pending','sandbox:'+key,'Awaiting explicit sandbox reconciliation')
        return PaymentResult('Settled','sandbox:'+key,'Synthetic settlement; no real funds')

class SandboxIdentity:
    def submit(self, *, key, identity, document, selfie):
        return {'reference':'sandbox:'+key,'status':'Pending',
                'signals':['Sandbox: OCR, liveness and biometric checks require manual fixture review']}

class SandboxNotifications:
    def send(self, **kwargs): return 'SandboxDelivered'

class UnconfiguredProvider:
    def execute(self, **kwargs): raise RuntimeError('Live payment provider is not configured')
    def submit(self, **kwargs): raise RuntimeError('Live KYC provider is not configured')
    def send(self, **kwargs): raise RuntimeError('Live notification provider is not configured')
