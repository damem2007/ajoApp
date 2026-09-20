"""Provider contracts and adapters.

Business/domain code depends on these normalized contracts rather than provider-
specific response objects. Sandbox providers are deterministic adapters; live
providers can be registered without changing Circle, Ledger or payment logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TransferRequest:
    key: str
    amount_minor: int
    currency: str
    kind: str
    bank_token: str


@dataclass(frozen=True)
class PaymentResult:
    status: str
    reference: str
    detail: str = ''


class PaymentProvider(Protocol):
    def link_bank(self, *, bank_token: str) -> dict: ...
    def initiate_transfer(self, request: TransferRequest) -> PaymentResult: ...
    def get_transfer(self, *, reference: str) -> PaymentResult: ...
    def cancel_transfer(self, *, reference: str, key: str) -> PaymentResult: ...


class IdentityProvider(Protocol):
    def submit(self, *, key: str, identity: dict, document: bytes, selfie: bytes) -> dict: ...


class NotificationProvider(Protocol):
    def send(self, *, key: str, channel: str, destination: str, title: str, body: str) -> str: ...


class SandboxPayments:
    def __init__(self):
        self._results = {}
        self._requests = {}

    def link_bank(self, *, bank_token):
        if not bank_token.startswith(('sandbox-ok-', 'sandbox-fail-', 'sandbox-pending-')):
            raise ValueError('Use a sandbox bank-account representation; raw bank credentials are not accepted')
        return {'masked': '•••• ' + bank_token[-4:], 'status': 'Verified'}

    def initiate_transfer(self, request: TransferRequest):
        previous=self._requests.get(request.key)
        if previous is not None:
            if previous != request:
                raise ValueError('Idempotency key already used for a different payment request')
            return self._results[request.key]
        self._requests[request.key]=request
        if request.bank_token.startswith('sandbox-fail-'):
            result=PaymentResult('Failed','sandbox:'+request.key,'Sandbox insufficient-funds scenario')
        elif request.bank_token.startswith('sandbox-pending-'):
            result=PaymentResult('Pending','sandbox:'+request.key,'Awaiting explicit sandbox reconciliation')
        else:
            result=PaymentResult('Settled','sandbox:'+request.key,'Synthetic settlement; no real funds')
        self._results[request.key]=result
        self._results[result.reference]=result
        return result

    # Backwards-compatible adapter method retained for existing call sites/tests.
    def execute(self, *, key, amount_minor, currency, kind, bank_token):
        return self.initiate_transfer(TransferRequest(key,amount_minor,currency,kind,bank_token))

    def get_transfer(self, *, reference):
        return self._results.get(reference, PaymentResult('Pending',reference,'Sandbox transfer requires explicit reconciliation'))

    def cancel_transfer(self, *, reference, key):
        result=PaymentResult('Failed',reference,'Sandbox transfer cancelled before settlement')
        self._results[reference]=result
        self._results[key]=result
        return result


class SandboxIdentity:
    def submit(self, *, key, identity, document, selfie):
        return {'reference':'sandbox:'+key,'status':'Pending',
                'signals':['Sandbox: OCR, liveness and biometric checks require manual fixture review']}


class SandboxNotifications:
    def send(self, **kwargs): return 'SandboxDelivered'


class UnconfiguredProvider:
    def link_bank(self, **kwargs): raise RuntimeError('Payment integration adapter is not implemented')
    def initiate_transfer(self, request): raise RuntimeError('Payment integration adapter is not implemented')
    def execute(self, **kwargs): raise RuntimeError('Payment integration adapter is not implemented')
    def get_transfer(self, **kwargs): raise RuntimeError('Payment integration adapter is not implemented')
    def cancel_transfer(self, **kwargs): raise RuntimeError('Payment integration adapter is not implemented')
    def submit(self, **kwargs): raise RuntimeError('Identity integration adapter is not implemented')
    def send(self, **kwargs): raise RuntimeError('Notification integration adapter is not implemented')


# Registration is application code, never arbitrary module paths from user input.
PROVIDERS = {
    'payments': {'sandbox': SandboxPayments, 'unconfigured': UnconfiguredProvider},
    'identity': {'sandbox': SandboxIdentity, 'unconfigured': UnconfiguredProvider},
    'notifications': {'sandbox': SandboxNotifications, 'unconfigured': UnconfiguredProvider},
}


def register_provider(kind, name, factory):
    if kind not in PROVIDERS or name in {'sandbox', 'unconfigured'}:
        raise ValueError('Invalid provider registration')
    PROVIDERS[kind][name] = factory


def resolve_provider(kind, name):
    factory = PROVIDERS.get(kind, {}).get(name)
    if factory is None:
        from app.config import ConfigurationError
        raise ConfigurationError('Selected ' + kind + ' provider has no registered adapter.')
    return factory()
