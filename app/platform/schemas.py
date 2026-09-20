from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator

Frequency = Literal['daily','weekly','bi-weekly','monthly','bi-monthly','quarterly','semi-annual','yearly']
class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Register(Input):
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=254)
    phone: str = Field(pattern=r'^\+[1-9][0-9]{7,14}$')
    password: str = Field(min_length=12, max_length=128)

class Login(Input):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    totp: Optional[str] = None

class Verify(Input):
    channel: Literal['email','sms']
    code: str = Field(pattern=r'^\d{6}$')

class KYCInput(Input):
    document_id: str
    selfie_id: str
    id_type: str = Field(max_length=50)
    id_number: str = Field(min_length=3, max_length=100)
    country: str = Field(pattern=r'^[A-Z]{2}$')
    province: str = Field(max_length=100, default='')
    expiry: date
    legal_name: str = Field(min_length=2, max_length=150)
    dob: date
    device_fingerprint: str = Field(min_length=8, max_length=200)

class CircleInput(Input):
    category: Literal['Travel','Education','Family','Community','Business'] = 'Community'
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=2000)
    privacy: Literal['public','private'] = 'public'
    premium: bool = False
    identities_hidden: bool = True
    currency: str = Field(pattern=r'^[A-Z]{3}$', default='NGN')
    target_minor: Optional[int] = Field(default=None, gt=0, le=9_000_000_000_000_000, strict=True)
    contribution_minor: Optional[int] = Field(default=None, gt=0, le=9_000_000_000_000_000, strict=True)
    minimum_members: int = Field(ge=2, le=500, default=3)
    planned_members: int = Field(ge=2, le=500, default=3)
    hard_cap: int = Field(ge=2, le=500, default=3)
    strict_minimum: bool = True
    allow_overflow: bool = False
    overflow_strategy: Optional[Literal['extend_rotation']] = None
    contribution_frequency: Frequency = 'monthly'
    collection_frequency: Frequency = 'monthly'
    payout_order_mode: Literal['manual','random'] = 'manual'
    invite_permission: Literal['creator-only','any-member'] = 'any-member'
    trust_threshold: int = Field(ge=0, le=100000, default=0)
    start_date: date
    timezone: Literal['UTC'] = 'UTC'

    @model_validator(mode='after')
    def consistent(self):
        if not self.minimum_members <= self.planned_members <= self.hard_cap:
            raise ValueError('Require minimum <= planned <= hard cap')
        if self.premium and self.privacy != 'public':
            raise ValueError('Premium is only available for public schemes')
        if self.contribution_minor is not None:
            from .calendar import contribution_dates
            derived=self.contribution_minor*len(contribution_dates(self.model_dump(mode='json'),self.planned_members))
            if derived>9_000_000_000_000_000:
                raise ValueError('The derived payout exceeds the supported amount')
            if self.target_minor is not None and self.target_minor!=derived:
                raise ValueError('Payout is derived from the fixed contribution amount and cycle schedule')
            self.target_minor=derived
        if self.target_minor is None:
            raise ValueError('Enter a contribution amount')
        if self.target_minor < self.hard_cap:
            raise ValueError('Target must support at least one minor unit per member')
        if self.allow_overflow:
            raise ValueError('Circle membership cannot exceed the planned member count')
        return self

class InviteInput(Input):
    max_uses: int = Field(ge=1, le=50, default=1)
    expires_hours: int = Field(ge=1, le=720, default=72)
    recipient_email: Optional[str] = Field(default=None, max_length=254)

class JoinInput(Input):
    code: Optional[str] = Field(default=None, max_length=200)

class FinalizeInput(Input):
    payout_order: list[str] = Field(default_factory=list, max_length=500)

class SignInput(Input):
    contract_hash: str
    typed_name: str = Field(min_length=2, max_length=150)
    accepted: Literal[True]

class Reason(Input):
    reason: str = Field(min_length=5, max_length=2000)

class ReviewInput(Reason):
    decision: Literal['Approved','Rejected','ResubmissionRequired','UnderReview']
    duplicate_reviewed: bool = False

class ComplaintInput(Input):
    circle_id: str
    target_id: Optional[str] = None
    category: Literal['non-payment','fraud','harassment','identity-concern','other']
    description: str = Field(min_length=10, max_length=4000)

class ResolutionInput(Reason):
    status: Literal['Triaged','UnderInvestigation','ActionTaken','Dismissed']
    assignee: Optional[str] = None
    trust_delta: int = Field(le=0, ge=-100, default=0)

class CircleSetup(Input):
    name_min_length: int = Field(default=3, ge=1, le=200)
    name_max_length: int = Field(default=80, ge=1, le=200)
    amount_max_minor: int = Field(default=100_000_000_000, gt=0, le=9_000_000_000_000_000)
    members_min: int = Field(default=2, ge=2, le=500)
    members_max: int = Field(default=50, ge=2, le=500)
    default_currency: str = 'NGN'
    contribution_frequencies: list[Frequency] = Field(default_factory=lambda: ['daily','weekly','bi-weekly','monthly','bi-monthly','quarterly','semi-annual','yearly'])
    collection_frequencies: list[Frequency] = Field(default_factory=lambda: ['daily','weekly','bi-weekly','monthly','bi-monthly','quarterly','semi-annual','yearly'])
    default_contribution_frequency: Frequency = 'monthly'
    default_collection_frequency: Frequency = 'monthly'
    allow_overflow: Literal[False] = False

    @model_validator(mode='after')
    def coherent(self):
        if self.name_min_length > self.name_max_length or self.members_min > self.members_max:
            raise ValueError('Minimum must not exceed maximum')
        if self.default_contribution_frequency not in self.contribution_frequencies or self.default_collection_frequency not in self.collection_frequencies:
            raise ValueError('Default frequencies must be enabled')
        return self

class CircleSetupResponse(CircleSetup):
    currencies: list[str]


class PlanPreview(Input):
    contribution_minor: int
    target_minor: int
    debit_dates: list[str]
    payout_dates: list[str]
    planned_members: int


class PolicyInput(Input):
    circle_setup: CircleSetup = Field(default_factory=CircleSetup)
    launch_countries: list[str] = Field(default_factory=list)
    currencies: list[str] = Field(default_factory=lambda:['NGN','CAD','USD','GBP'])
    id_types: dict[str,list[str]] = Field(default_factory=dict)
    legal_approved: bool = False
    terms: str = Field(default='SANDBOX ONLY. No real money moves. Members contribute the amounts in the schedule and receive one payout. Staff may access identities for compliance review.', max_length=20000)
    mixed_frequency_policy: Optional[Literal['payout_window']] = None
    calendar_policy: Optional[Literal['utc_calendar_clip']] = None
    overflow_strategy: Optional[Literal['extend_rotation']] = None
    random_policy: Optional[Literal['server_commitment']] = None
    default_policy: Optional[Literal['hold_payout_flag_member']] = None
    fee_mode: Optional[Literal['none','per_contribution']] = None
    fee_flat_minor: int = Field(ge=0, le=100000, default=0)
    fee_bps: int = Field(ge=0, le=1000, default=0)
    retries: int = Field(ge=0, le=10, default=3)
    retry_days: int = Field(ge=1, le=30, default=1)
    grace_days: int = Field(ge=0, le=90, default=3)
    completion_points: int = Field(ge=0, le=1000, default=10)
    default_penalty: int = Field(ge=0, le=100, default=5)
    inviter_penalty_bps: int = Field(ge=0, le=10000, default=2000)
    tiers: list[dict[str,int]] = Field(default_factory=lambda:[{'score':0,'cap':1},{'score':10,'cap':3},{'score':50,'cap':5}])
    scheduler_paused: bool = False
    retention_days: Optional[int] = Field(default=None, ge=1)
    complaint_sla_days: int = Field(ge=1, le=90, default=3)
    notification_templates: dict[str,str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_tiers(self):
        import re
        if not self.currencies or len(set(self.currencies)) != len(self.currencies) or any(not re.fullmatch(r'[A-Z]{3}', c) for c in self.currencies):
            raise ValueError('Currencies must be unique three-letter uppercase codes')
        if self.circle_setup.default_currency not in self.currencies:
            raise ValueError("Default circle currency must be enabled")
        if not self.tiers or any(set(t) != {'score','cap'} or t['cap'] < 1 or t['score'] < 0 for t in self.tiers):
            raise ValueError('Each tier needs a nonnegative score and a positive cap')
        if min(t['score'] for t in self.tiers) != 0:
            raise ValueError('A base score-zero tier is required')
        if self.fee_mode != 'per_contribution' and (self.fee_bps or self.fee_flat_minor):
            raise ValueError('Nonzero fees require per_contribution fee mode')
        return self

class PolicyChange(Input):
    policy: PolicyInput
    reason: str = Field(min_length=5, max_length=2000)

class BankInput(Input):
    provider_token: str = Field(min_length=8, max_length=500)
    mandate_accepted: Literal[True]

class Preferences(Input):
    email: bool = True
    sms: bool = True
    push: bool = True
    locale: str = Field(default='en', max_length=10)
    push_token: Optional[str] = Field(default=None, max_length=500)

class ParticipantConfigChange(Reason):
    tiers: list[dict[str, int]] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def validated_tiers(self):
        PolicyInput(tiers=self.tiers)
        if len({tier['score'] for tier in self.tiers}) != len(self.tiers):
            raise ValueError('Each score threshold must be unique')
        return self
