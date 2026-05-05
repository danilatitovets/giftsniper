from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import OID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class User(Base):
    __tablename__ = 'users'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='users_pkey'),
        UniqueConstraint('telegram_id', name='users_telegram_id_key'),
        Index('ix_users_is_blocked', 'is_blocked'),
        Index('ix_users_plan', 'plan'),
        Index('ix_users_role', 'role')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
    )
    risk_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="TON")
    check_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'user'::character varying"))
    plan: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'free'::character varying"))
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    command_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    username: Mapped[Optional[str]] = mapped_column(String(255))
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    bankroll_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    goal_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    max_deal_percent: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('25'))
    max_collection_percent: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('40'))
    reserve_percent: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('20'))
    plan_expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    first_seen_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_seen_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    bonus_checks_available: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))

    alert_rules: Mapped[list['AlertRule']] = relationship('AlertRule', back_populates='user')
    audit_logs: Mapped[list['AuditLog']] = relationship('AuditLog', back_populates='user')
    beta_invites: Mapped[list['BetaInvite']] = relationship('BetaInvite', back_populates='created_by_user')
    billing_events: Mapped[list['BillingEvent']] = relationship('BillingEvent', back_populates='user')
    entitlement_overrides_created_by_user: Mapped[list['EntitlementOverride']] = relationship('EntitlementOverride', foreign_keys='[EntitlementOverride.created_by_user_id]', back_populates='created_by_user')
    entitlement_overrides_user: Mapped[list['EntitlementOverride']] = relationship('EntitlementOverride', foreign_keys='[EntitlementOverride.user_id]', back_populates='user')
    gifts: Mapped[list['Gift']] = relationship('Gift', back_populates='user')
    listings: Mapped[list['Listing']] = relationship('Listing', back_populates='user')
    manual_payment_requests_confirmed_by_user: Mapped[list['ManualPaymentRequest']] = relationship('ManualPaymentRequest', foreign_keys='[ManualPaymentRequest.confirmed_by_user_id]', back_populates='confirmed_by_user')
    manual_payment_requests_reviewed_by_user: Mapped[list['ManualPaymentRequest']] = relationship('ManualPaymentRequest', foreign_keys='[ManualPaymentRequest.reviewed_by_user_id]', back_populates='reviewed_by_user')
    manual_payment_requests_user: Mapped[list['ManualPaymentRequest']] = relationship('ManualPaymentRequest', foreign_keys='[ManualPaymentRequest.user_id]', back_populates='user')
    market_snapshots: Mapped[list['MarketSnapshot']] = relationship('MarketSnapshot', back_populates='user')
    payment_webhook_events: Mapped[list['PaymentWebhookEvent']] = relationship('PaymentWebhookEvent', back_populates='user')
    product_events: Mapped[list['ProductEvent']] = relationship('ProductEvent', back_populates='user')
    sales: Mapped[list['Sale']] = relationship('Sale', back_populates='user')
    signal_snapshots: Mapped[list['SignalSnapshot']] = relationship('SignalSnapshot', back_populates='user')
    smart_alert_incidents_acknowledged_by_user: Mapped[list['SmartAlertIncident']] = relationship('SmartAlertIncident', foreign_keys='[SmartAlertIncident.acknowledged_by_user_id]', back_populates='acknowledged_by_user')
    smart_alert_incidents_user: Mapped[list['SmartAlertIncident']] = relationship('SmartAlertIncident', foreign_keys='[SmartAlertIncident.user_id]', back_populates='user')
    smart_alert_states: Mapped[list['SmartAlertState']] = relationship('SmartAlertState', back_populates='user')
    trait_floors: Mapped[list['TraitFloor']] = relationship('TraitFloor', back_populates='user')
    user_entitlements: Mapped['UserEntitlement'] = relationship('UserEntitlement', uselist=False, back_populates='user')
    user_notification_settings: Mapped['UserNotificationSettings'] = relationship('UserNotificationSettings', uselist=False, back_populates='user')
    user_universe_collections: Mapped[list['UserUniverseCollection']] = relationship('UserUniverseCollection', back_populates='user')
    beta_invite_redemptions: Mapped[list['BetaInviteRedemption']] = relationship('BetaInviteRedemption', back_populates='user')
    feedback_items_reviewed_by_user: Mapped[list['FeedbackItem']] = relationship('FeedbackItem', foreign_keys='[FeedbackItem.reviewed_by_user_id]', back_populates='reviewed_by_user')
    feedback_items_user: Mapped[list['FeedbackItem']] = relationship('FeedbackItem', foreign_keys='[FeedbackItem.user_id]', back_populates='user')
    smart_alert_events: Mapped[list['SmartAlertEvent']] = relationship('SmartAlertEvent', back_populates='user')
    smart_alert_incident_actions: Mapped[list['SmartAlertIncidentAction']] = relationship('SmartAlertIncidentAction', back_populates='user')
    trade_journal: Mapped[list['TradeJournal']] = relationship('TradeJournal', back_populates='user')
    ton_subscription_payments: Mapped[list['TonSubscriptionPayment']] = relationship(
        'TonSubscriptionPayment', back_populates='user'
    )


class AlertRule(Base):
    __tablename__ = 'alert_rules'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='alert_rules_user_id_fkey'),
        PrimaryKeyConstraint('id', name='alert_rules_pkey')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    last_is_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    trigger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'price'::character varying"))
    collection: Mapped[Optional[str]] = mapped_column(String(255))
    trait_type: Mapped[Optional[str]] = mapped_column(String(255))
    trait_value: Mapped[Optional[str]] = mapped_column(String(255))
    max_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    min_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    last_checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_triggered_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_value_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    threshold_value: Mapped[Optional[float]] = mapped_column(Double(53))
    threshold_type: Mapped[Optional[str]] = mapped_column(String(32))
    cooldown_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    last_payload_hash: Mapped[Optional[str]] = mapped_column(String(128))

    user: Mapped['User'] = relationship('User', back_populates='alert_rules')


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL', name='audit_logs_user_id_fkey'),
        PrimaryKeyConstraint('id', name='audit_logs_pkey'),
        Index('ix_audit_logs_action', 'action'),
        Index('ix_audit_logs_created_at', 'created_at'),
        Index('ix_audit_logs_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64))
    entity_id: Mapped[Optional[str]] = mapped_column(String(128))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)

    user: Mapped[Optional['User']] = relationship('User', back_populates='audit_logs')


class BetaInvite(Base):
    __tablename__ = 'beta_invites'
    __table_args__ = (
        ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL', name='beta_invites_created_by_user_id_fkey'),
        PrimaryKeyConstraint('id', name='beta_invites_pkey'),
        UniqueConstraint('code', name='uq_beta_invites_code'),
        Index('ix_beta_invites_code', 'code'),
        Index('ix_beta_invites_is_active', 'is_active')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    plan: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pro'::character varying"))
    days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('14'))
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    created_by_user: Mapped[Optional['User']] = relationship('User', back_populates='beta_invites')
    beta_invite_redemptions: Mapped[list['BetaInviteRedemption']] = relationship('BetaInviteRedemption', back_populates='invite')


class BillingEvent(Base):
    __tablename__ = 'billing_events'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL', name='billing_events_user_id_fkey'),
        PrimaryKeyConstraint('id', name='billing_events_pkey'),
        Index('ix_billing_events_event_type', 'event_type'),
        Index('ix_billing_events_provider_event_id', 'provider_event_id'),
        Index('ix_billing_events_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    provider: Mapped[Optional[str]] = mapped_column(String(32))
    provider_event_id: Mapped[Optional[str]] = mapped_column(String(255))
    plan: Mapped[Optional[str]] = mapped_column(String(16))
    amount: Mapped[Optional[float]] = mapped_column(Double(53))
    currency: Mapped[Optional[str]] = mapped_column(String(16))
    status: Mapped[Optional[str]] = mapped_column(String(32))
    metadata_json: Mapped[Optional[str]] = mapped_column(String(4000))

    user: Mapped[Optional['User']] = relationship('User', back_populates='billing_events')


class EntitlementOverride(Base):
    __tablename__ = 'entitlement_overrides'
    __table_args__ = (
        ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL', name='entitlement_overrides_created_by_user_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='entitlement_overrides_user_id_fkey'),
        PrimaryKeyConstraint('id', name='entitlement_overrides_pkey'),
        Index('ix_entitlement_overrides_is_active', 'is_active'),
        Index('ix_entitlement_overrides_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    plan: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(4000))
    created_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    created_by_user: Mapped[Optional['User']] = relationship('User', foreign_keys=[created_by_user_id], back_populates='entitlement_overrides_created_by_user')
    user: Mapped['User'] = relationship('User', foreign_keys=[user_id], back_populates='entitlement_overrides_user')


class Gift(Base):
    __tablename__ = 'gifts'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='gifts_user_id_fkey'),
        PrimaryKeyConstraint('id', name='gifts_pkey'),
        UniqueConstraint('user_id', 'collection', 'number', name='uq_user_gift'),
        Index('ix_gifts_collection_number_lookup', 'collection', 'number'),
        Index('ix_gifts_nft_address_lookup', 'nft_address'),
        Index('ix_gifts_user_canonical_key', 'user_id', 'canonical_key'),
        Index('ix_gifts_user_normalized_collection', 'user_id', 'normalized_collection')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    collection: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    image_url: Mapped[Optional[str]] = mapped_column(String(1024))
    purchase_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    target_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    nft_address: Mapped[Optional[str]] = mapped_column(String(256))
    collection_address: Mapped[Optional[str]] = mapped_column(String(256))
    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    marketplace: Mapped[Optional[str]] = mapped_column(String(64))
    canonical_key: Mapped[Optional[str]] = mapped_column(String(384))
    normalized_collection: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    attributes_json: Mapped[Optional[str]] = mapped_column(Text)
    last_resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    identity_confidence: Mapped[Optional[int]] = mapped_column(Integer)
    signals_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_signal_checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_signal_sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_signal_normal_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    last_signal_floor_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    last_signal_market_hash: Mapped[Optional[str]] = mapped_column(String(256))

    user: Mapped['User'] = relationship('User', back_populates='gifts')
    analysis_results: Mapped[list['AnalysisResult']] = relationship('AnalysisResult', back_populates='gift')
    gift_attributes: Mapped[list['GiftAttribute']] = relationship('GiftAttribute', back_populates='gift')


class Listing(Base):
    __tablename__ = 'listings'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_listings_user_id'),
        PrimaryKeyConstraint('id', name='listings_pkey'),
        UniqueConstraint('external_id', name='listings_external_id_key'),
        Index('ix_listings_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    collection: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    price_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    attributes_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(1024))
    user_id: Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped[Optional['User']] = relationship('User', back_populates='listings')


class ManualPaymentRequest(Base):
    __tablename__ = 'manual_payment_requests'
    __table_args__ = (
        ForeignKeyConstraint(['confirmed_by_user_id'], ['users.id'], ondelete='SET NULL', name='manual_payment_requests_confirmed_by_user_id_fkey'),
        ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], ondelete='SET NULL', name='fk_manual_payment_requests_reviewed_by'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='manual_payment_requests_user_id_fkey'),
        PrimaryKeyConstraint('id', name='manual_payment_requests_pkey'),
        Index('ix_manual_payment_requests_created_at', 'created_at'),
        Index('ix_manual_payment_requests_requested_plan', 'requested_plan'),
        Index('ix_manual_payment_requests_status', 'status'),
        Index('ix_manual_payment_requests_tx_hash', 'tx_hash'),
        Index('ix_manual_payment_requests_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_plan: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'TON'::character varying"))
    wallet_address: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    amount: Mapped[Optional[float]] = mapped_column(Double(53))
    tx_hash: Mapped[Optional[str]] = mapped_column(String(255))
    proof_text: Mapped[Optional[str]] = mapped_column(String(4000))
    admin_note: Mapped[Optional[str]] = mapped_column(String(4000))
    confirmed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    confirmed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    rejected_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    confirmed_by_user: Mapped[Optional['User']] = relationship('User', foreign_keys=[confirmed_by_user_id], back_populates='manual_payment_requests_confirmed_by_user')
    reviewed_by_user: Mapped[Optional['User']] = relationship('User', foreign_keys=[reviewed_by_user_id], back_populates='manual_payment_requests_reviewed_by_user')
    user: Mapped['User'] = relationship('User', foreign_keys=[user_id], back_populates='manual_payment_requests_user')


class TonSubscriptionPayment(Base):
    __tablename__ = "ton_subscription_payments"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="ton_subscription_payments_user_id_fkey"),
        PrimaryKeyConstraint("id", name="ton_subscription_payments_pkey"),
        UniqueConstraint("comment", name="uq_ton_subscription_payments_comment"),
        UniqueConstraint("tx_hash", name="uq_ton_subscription_payments_tx_hash"),
        Index("ix_ton_subscription_payments_user_id", "user_id"),
        Index("ix_ton_subscription_payments_status", "status"),
        Index("ix_ton_subscription_payments_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    plan: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    amount_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    receiver_address: Mapped[str] = mapped_column(String(128), nullable=False)
    comment: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'::character varying"))
    tx_hash: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship("User", back_populates="ton_subscription_payments")


class TonPaymentConsumedTx(Base):
    __tablename__ = "ton_payment_consumed_tx"
    __table_args__ = (
        PrimaryKeyConstraint("tx_hash", name="ton_payment_consumed_tx_pkey"),
        ForeignKeyConstraint(["payment_id"], ["ton_subscription_payments.id"], ondelete="CASCADE", name="ton_payment_consumed_tx_payment_id_fkey"),
    )

    tx_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    payment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class UserNftCheckDay(Base):
    __tablename__ = "user_nft_check_day"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="user_nft_check_day_user_id_fkey"),
        PrimaryKeyConstraint("user_id", "day", name="user_nft_check_day_pkey"),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    checks_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class UserReferral(Base):
    __tablename__ = "user_referrals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["referrer_user_id"], ["users.id"], ondelete="CASCADE", name="user_referrals_referrer_user_id_fkey"
        ),
        ForeignKeyConstraint(
            ["invited_user_id"], ["users.id"], ondelete="CASCADE", name="user_referrals_invited_user_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="user_referrals_pkey"),
        UniqueConstraint("invited_user_id", name="user_referrals_invited_user_id_key"),
        CheckConstraint("referrer_user_id <> invited_user_id", name="user_referrals_no_self"),
        Index("ix_user_referrals_referrer_user_id", "referrer_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invited_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
    )
    bonus_awarded_checks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    milestone_awarded_checks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    source_payload: Mapped[Optional[str]] = mapped_column(String(512))


class MarketSnapshot(Base):
    __tablename__ = 'market_snapshots'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_market_snapshots_user_id'),
        PrimaryKeyConstraint('id', name='market_snapshots_pkey'),
        Index('ix_market_snapshots_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    floor_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    volume_24h_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    listed_count: Mapped[Optional[int]] = mapped_column(Integer)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped[Optional['User']] = relationship('User', back_populates='market_snapshots')


class PaymentWebhookEvent(Base):
    __tablename__ = 'payment_webhook_events'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL', name='payment_webhook_events_user_id_fkey'),
        PrimaryKeyConstraint('id', name='payment_webhook_events_pkey'),
        UniqueConstraint('provider', 'provider_event_id', name='uq_payment_provider_event'),
        Index('ix_payment_webhook_events_created_at', 'created_at'),
        Index('ix_payment_webhook_events_provider', 'provider'),
        Index('ix_payment_webhook_events_provider_event_id', 'provider_event_id'),
        Index('ix_payment_webhook_events_status', 'status'),
        Index('ix_payment_webhook_events_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    provider_event_id: Mapped[Optional[str]] = mapped_column(String(255))
    event_type: Mapped[Optional[str]] = mapped_column(String(64))
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    plan: Mapped[Optional[str]] = mapped_column(String(16))
    amount: Mapped[Optional[float]] = mapped_column(Double(53))
    currency: Mapped[Optional[str]] = mapped_column(String(16))
    sanitized_payload_json: Mapped[Optional[str]] = mapped_column(String(4000))
    sanitized_headers_json: Mapped[Optional[str]] = mapped_column(String(4000))
    last_error: Mapped[Optional[str]] = mapped_column(String(2000))
    processed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    user: Mapped[Optional['User']] = relationship('User', back_populates='payment_webhook_events')


class ProductEvent(Base):
    __tablename__ = 'product_events'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL', name='product_events_user_id_fkey'),
        PrimaryKeyConstraint('id', name='product_events_pkey'),
        Index('ix_product_events_command', 'command'),
        Index('ix_product_events_created_at', 'created_at'),
        Index('ix_product_events_event_type', 'event_type'),
        Index('ix_product_events_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
    )
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    command: Mapped[Optional[str]] = mapped_column(String(64))
    metadata_json: Mapped[Optional[str]] = mapped_column(String(4000))

    user: Mapped[Optional['User']] = relationship('User', back_populates='product_events')


class Sale(Base):
    __tablename__ = 'sales'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_sales_user_id'),
        PrimaryKeyConstraint('id', name='sales_pkey'),
        UniqueConstraint('external_id', name='sales_external_id_key'),
        Index('ix_sales_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    collection: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    price_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    sold_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    attributes_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped[Optional['User']] = relationship('User', back_populates='sales')


class SignalSnapshot(Base):
    __tablename__ = 'signal_snapshots'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='signal_snapshots_user_id_fkey'),
        PrimaryKeyConstraint('id', name='signal_snapshots_pkey'),
        Index('ix_signal_snapshots_collection', 'collection'),
        Index('ix_signal_snapshots_created_at', 'created_at'),
        Index('ix_signal_snapshots_decision_type', 'decision_type'),
        Index('ix_signal_snapshots_source_command', 'source_command'),
        Index('ix_signal_snapshots_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_command: Mapped[str] = mapped_column(String(32), nullable=False)
    collection: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    number: Mapped[Optional[int]] = mapped_column(Integer)
    nft_address: Mapped[Optional[str]] = mapped_column(String(256))
    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    input_text: Mapped[Optional[str]] = mapped_column(String(2000))
    decision_type: Mapped[Optional[str]] = mapped_column(String(32))
    recommendation: Mapped[Optional[str]] = mapped_column(String(64))
    tier: Mapped[Optional[str]] = mapped_column(String(64))
    score: Mapped[Optional[int]] = mapped_column(Integer)
    safe_buy_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    max_buy_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    list_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    quick_sell_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    stop_loss_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    expected_profit_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    expected_roi_percent: Mapped[Optional[float]] = mapped_column(Double(53))
    confidence_score: Mapped[Optional[int]] = mapped_column(Integer)
    risk_score: Mapped[Optional[int]] = mapped_column(Integer)
    liquidity_score: Mapped[Optional[int]] = mapped_column(Integer)
    market_regime: Mapped[Optional[str]] = mapped_column(String(32))
    source_quality: Mapped[Optional[str]] = mapped_column(String(255))
    freshness_label: Mapped[Optional[str]] = mapped_column(String(32))
    has_recent_sales: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_trait_sales: Mapped[Optional[bool]] = mapped_column(Boolean)
    important_trait_detected: Mapped[Optional[bool]] = mapped_column(Boolean)
    warning_flags_json: Mapped[Optional[dict]] = mapped_column(JSON)
    analysis_json: Mapped[Optional[dict]] = mapped_column(JSON)

    user: Mapped['User'] = relationship('User', back_populates='signal_snapshots')
    feedback_items: Mapped[list['FeedbackItem']] = relationship('FeedbackItem', back_populates='signal_snapshot')
    trade_journal: Mapped[list['TradeJournal']] = relationship('TradeJournal', back_populates='signal_snapshot')


class SmartAlertIncident(Base):
    __tablename__ = 'smart_alert_incidents'
    __table_args__ = (
        ForeignKeyConstraint(['acknowledged_by_user_id'], ['users.id'], ondelete='SET NULL', name='fk_smart_alert_incidents_ack_user'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='smart_alert_incidents_user_id_fkey'),
        PrimaryKeyConstraint('id', name='smart_alert_incidents_pkey'),
        Index('ix_smart_alert_incidents_acknowledged_at', 'acknowledged_at'),
        Index('ix_smart_alert_incidents_alert_type', 'alert_type'),
        Index('ix_smart_alert_incidents_collection', 'collection'),
        Index('ix_smart_alert_incidents_is_false_positive', 'is_false_positive'),
        Index('ix_smart_alert_incidents_last_seen_at', 'last_seen_at'),
        Index('ix_smart_alert_incidents_muted_until', 'muted_until'),
        Index('ix_smart_alert_incidents_severity', 'severity'),
        Index('ix_smart_alert_incidents_status', 'status'),
        Index('ix_smart_alert_incidents_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'open'::character varying"))
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    is_false_positive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    collection: Mapped[Optional[str]] = mapped_column(String(255))
    recovered_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_payload_hash: Mapped[Optional[str]] = mapped_column(String(128))
    summary: Mapped[Optional[str]] = mapped_column(String(4000))
    acknowledged_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    acknowledged_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    muted_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    mute_reason: Mapped[Optional[str]] = mapped_column(String(4000))
    resolved_manually_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    resolved_note: Mapped[Optional[str]] = mapped_column(String(4000))
    false_positive_note: Mapped[Optional[str]] = mapped_column(String(4000))

    acknowledged_by_user: Mapped[Optional['User']] = relationship('User', foreign_keys=[acknowledged_by_user_id], back_populates='smart_alert_incidents_acknowledged_by_user')
    user: Mapped['User'] = relationship('User', foreign_keys=[user_id], back_populates='smart_alert_incidents_user')
    smart_alert_events: Mapped[list['SmartAlertEvent']] = relationship('SmartAlertEvent', back_populates='incident')
    smart_alert_incident_actions: Mapped[list['SmartAlertIncidentAction']] = relationship('SmartAlertIncidentAction', back_populates='incident')


class SmartAlertState(Base):
    __tablename__ = 'smart_alert_states'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='smart_alert_states_user_id_fkey'),
        PrimaryKeyConstraint('id', name='smart_alert_states_pkey'),
        UniqueConstraint('user_id', 'alert_type', 'collection', name='uq_smart_alert_state_scope'),
        Index('ix_smart_alert_states_alert_type', 'alert_type'),
        Index('ix_smart_alert_states_collection', 'collection'),
        Index('ix_smart_alert_states_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    collection: Mapped[Optional[str]] = mapped_column(String(255))
    last_regime: Mapped[Optional[str]] = mapped_column(String(32))
    last_strength_score: Mapped[Optional[float]] = mapped_column(Double(53))
    last_liquidity_score: Mapped[Optional[float]] = mapped_column(Double(53))
    last_payload_hash: Mapped[Optional[str]] = mapped_column(String(128))
    last_sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    user: Mapped['User'] = relationship('User', back_populates='smart_alert_states')


class TraitFloor(Base):
    __tablename__ = 'trait_floors'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_trait_floors_user_id'),
        PrimaryKeyConstraint('id', name='trait_floors_pkey'),
        Index('ix_trait_floors_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection: Mapped[str] = mapped_column(String(255), nullable=False)
    trait_type: Mapped[str] = mapped_column(String(255), nullable=False)
    trait_value: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    floor_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped[Optional['User']] = relationship('User', back_populates='trait_floors')


class UserEntitlement(Base):
    __tablename__ = 'user_entitlements'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='user_entitlements_user_id_fkey'),
        PrimaryKeyConstraint('id', name='user_entitlements_pkey'),
        UniqueConstraint('user_id', name='uq_user_entitlements_user_id'),
        Index('ix_user_entitlements_expires_at', 'expires_at'),
        Index('ix_user_entitlements_plan', 'plan'),
        Index('ix_user_entitlements_status', 'status'),
        Index('ix_user_entitlements_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    plan: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    starts_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    grace_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    canceled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    user: Mapped['User'] = relationship('User', back_populates='user_entitlements')


class UserNotificationSettings(Base):
    __tablename__ = 'user_notification_settings'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='user_notification_settings_user_id_fkey'),
        PrimaryKeyConstraint('id', name='user_notification_settings_pkey'),
        UniqueConstraint('user_id', name='user_notification_settings_user_id_key'),
        Index('ix_user_notification_settings_user_id', 'user_id', unique=True)
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'smart'::character varying"))
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    digest_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('180'))
    min_severity_to_notify: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'warning'::character varying"))
    critical_ignore_quiet_hours: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    quiet_hours_start: Mapped[Optional[str]] = mapped_column(String(8))
    quiet_hours_end: Mapped[Optional[str]] = mapped_column(String(8))

    user: Mapped['User'] = relationship('User', back_populates='user_notification_settings')


class UserUniverseCollection(Base):
    __tablename__ = 'user_universe_collections'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='user_universe_collections_user_id_fkey'),
        PrimaryKeyConstraint('id', name='user_universe_collections_pkey'),
        Index('ix_user_universe_collections_collection', 'collection'),
        Index('ix_user_universe_collections_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    collection: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped['User'] = relationship('User', back_populates='user_universe_collections')


class AnalysisResult(Base):
    __tablename__ = 'analysis_results'
    __table_args__ = (
        ForeignKeyConstraint(['gift_id'], ['gifts.id'], ondelete='CASCADE', name='analysis_results_gift_id_fkey'),
        PrimaryKeyConstraint('id', name='analysis_results_pkey')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gift_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quick_sell_price_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    fair_price_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    optimistic_price_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    max_buy_price_ton: Mapped[float] = mapped_column(Double(53), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    buy_zone_min_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    buy_zone_max_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    list_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    stop_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    marketplace_fee_percent: Mapped[Optional[float]] = mapped_column(Double(53))
    expected_net_sale_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    expected_profit_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    expected_roi_percent: Mapped[Optional[float]] = mapped_column(Double(53))
    liquidity_score: Mapped[Optional[int]] = mapped_column(Integer)
    risk_score: Mapped[Optional[int]] = mapped_column(Integer)
    safe_buy_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    aggressive_buy_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    quick_flip_list_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    normal_list_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    high_list_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    downside_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    upside_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    time_to_sell_estimate: Mapped[Optional[str]] = mapped_column(String(64))
    decision_type: Mapped[Optional[str]] = mapped_column(String(32))
    decision_summary: Mapped[Optional[str]] = mapped_column(String(512))
    rarity_score: Mapped[Optional[float]] = mapped_column(Double(53))
    liquidity_adjusted_rarity_score: Mapped[Optional[float]] = mapped_column(Double(53))
    trait_opportunity_score: Mapped[Optional[float]] = mapped_column(Double(53))
    market_intelligence_json: Mapped[Optional[str]] = mapped_column(Text)
    precision_plan_json: Mapped[Optional[str]] = mapped_column(Text)
    decision_json: Mapped[Optional[str]] = mapped_column(Text)

    gift: Mapped['Gift'] = relationship('Gift', back_populates='analysis_results')


class BetaInviteRedemption(Base):
    __tablename__ = 'beta_invite_redemptions'
    __table_args__ = (
        ForeignKeyConstraint(['invite_id'], ['beta_invites.id'], ondelete='CASCADE', name='beta_invite_redemptions_invite_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='beta_invite_redemptions_user_id_fkey'),
        PrimaryKeyConstraint('id', name='beta_invite_redemptions_pkey'),
        Index('ix_beta_invite_redemptions_invite_id', 'invite_id'),
        Index('ix_beta_invite_redemptions_redeemed_at', 'redeemed_at'),
        Index('ix_beta_invite_redemptions_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invite_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    redeemed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

    invite: Mapped['BetaInvite'] = relationship('BetaInvite', back_populates='beta_invite_redemptions')
    user: Mapped['User'] = relationship('User', back_populates='beta_invite_redemptions')


class FeedbackItem(Base):
    __tablename__ = 'feedback_items'
    __table_args__ = (
        ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], ondelete='SET NULL', name='fk_feedback_items_reviewed_by_user_id_users'),
        ForeignKeyConstraint(['signal_snapshot_id'], ['signal_snapshots.id'], ondelete='SET NULL', name='fk_feedback_items_signal_snapshot_id'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='feedback_items_user_id_fkey'),
        PrimaryKeyConstraint('id', name='feedback_items_pkey'),
        Index('ix_feedback_items_created_at', 'created_at'),
        Index('ix_feedback_items_priority', 'priority'),
        Index('ix_feedback_items_signal_snapshot_id', 'signal_snapshot_id'),
        Index('ix_feedback_items_status', 'status'),
        Index('ix_feedback_items_type', 'type'),
        Index('ix_feedback_items_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(4000), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'new'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'normal'::character varying"))
    admin_note: Mapped[Optional[str]] = mapped_column(String(2000))
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    signal_snapshot_id: Mapped[Optional[int]] = mapped_column(Integer)
    signal_rating: Mapped[Optional[str]] = mapped_column(String(32))
    outcome_hint: Mapped[Optional[str]] = mapped_column(String(64))
    reviewer_note: Mapped[Optional[str]] = mapped_column(String(2000))

    reviewed_by_user: Mapped[Optional['User']] = relationship('User', foreign_keys=[reviewed_by_user_id], back_populates='feedback_items_reviewed_by_user')
    signal_snapshot: Mapped[Optional['SignalSnapshot']] = relationship('SignalSnapshot', back_populates='feedback_items')
    user: Mapped['User'] = relationship('User', foreign_keys=[user_id], back_populates='feedback_items_user')


class GiftAttribute(Base):
    __tablename__ = 'gift_attributes'
    __table_args__ = (
        ForeignKeyConstraint(['gift_id'], ['gifts.id'], ondelete='CASCADE', name='gift_attributes_gift_id_fkey'),
        PrimaryKeyConstraint('id', name='gift_attributes_pkey')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gift_id: Mapped[int] = mapped_column(Integer, nullable=False)
    trait_type: Mapped[str] = mapped_column(String(255), nullable=False)
    trait_value: Mapped[str] = mapped_column(String(255), nullable=False)
    rarity_percent: Mapped[Optional[float]] = mapped_column(Double(53))

    gift: Mapped['Gift'] = relationship('Gift', back_populates='gift_attributes')


class SmartAlertEvent(Base):
    __tablename__ = 'smart_alert_events'
    __table_args__ = (
        ForeignKeyConstraint(['incident_id'], ['smart_alert_incidents.id'], ondelete='SET NULL', name='fk_smart_alert_events_incident_id'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='smart_alert_events_user_id_fkey'),
        PrimaryKeyConstraint('id', name='smart_alert_events_pkey'),
        Index('ix_smart_alert_events_alert_type', 'alert_type'),
        Index('ix_smart_alert_events_created_at', 'created_at'),
        Index('ix_smart_alert_events_incident_id', 'incident_id'),
        Index('ix_smart_alert_events_severity', 'severity'),
        Index('ix_smart_alert_events_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(String(4000), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    is_batched: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    collection: Mapped[Optional[str]] = mapped_column(String(255))
    sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    incident_id: Mapped[Optional[int]] = mapped_column(Integer)

    incident: Mapped[Optional['SmartAlertIncident']] = relationship('SmartAlertIncident', back_populates='smart_alert_events')
    user: Mapped['User'] = relationship('User', back_populates='smart_alert_events')


class SmartAlertIncidentAction(Base):
    __tablename__ = 'smart_alert_incident_actions'
    __table_args__ = (
        ForeignKeyConstraint(['incident_id'], ['smart_alert_incidents.id'], ondelete='CASCADE', name='smart_alert_incident_actions_incident_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='smart_alert_incident_actions_user_id_fkey'),
        PrimaryKeyConstraint('id', name='smart_alert_incident_actions_pkey'),
        Index('ix_smart_alert_incident_actions_action_type', 'action_type'),
        Index('ix_smart_alert_incident_actions_created_at', 'created_at'),
        Index('ix_smart_alert_incident_actions_incident_id', 'incident_id'),
        Index('ix_smart_alert_incident_actions_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(4000))

    incident: Mapped['SmartAlertIncident'] = relationship('SmartAlertIncident', back_populates='smart_alert_incident_actions')
    user: Mapped['User'] = relationship('User', back_populates='smart_alert_incident_actions')


class TradeJournal(Base):
    __tablename__ = 'trade_journal'
    __table_args__ = (
        ForeignKeyConstraint(['signal_snapshot_id'], ['signal_snapshots.id'], ondelete='SET NULL', name='fk_trade_journal_signal_snapshot_id'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='trade_journal_user_id_fkey'),
        PrimaryKeyConstraint('id', name='trade_journal_pkey'),
        Index('ix_trade_journal_signal_snapshot_id', 'signal_snapshot_id'),
        Index('ix_trade_journal_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    collection: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'open'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    number: Mapped[Optional[int]] = mapped_column(Integer)
    nft_address: Mapped[Optional[str]] = mapped_column(String(256))
    attributes_json: Mapped[Optional[dict]] = mapped_column(JSON)
    buy_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    buy_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    sell_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    sell_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    prediction_json: Mapped[Optional[str]] = mapped_column(Text)
    decision_type: Mapped[Optional[str]] = mapped_column(String(32))
    predicted_safe_buy_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    predicted_max_buy_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    predicted_list_price_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    predicted_roi_percent: Mapped[Optional[float]] = mapped_column(Double(53))
    predicted_confidence: Mapped[Optional[int]] = mapped_column(Integer)
    accuracy_tags_json: Mapped[Optional[dict]] = mapped_column(JSON)
    realized_profit_ton: Mapped[Optional[float]] = mapped_column(Double(53))
    realized_roi_percent: Mapped[Optional[float]] = mapped_column(Double(53))
    hold_time_hours: Mapped[Optional[float]] = mapped_column(Double(53))
    prediction_error_json: Mapped[Optional[str]] = mapped_column(Text)
    signal_snapshot_id: Mapped[Optional[int]] = mapped_column(Integer)

    signal_snapshot: Mapped[Optional['SignalSnapshot']] = relationship('SignalSnapshot', back_populates='trade_journal')
    user: Mapped['User'] = relationship('User', back_populates='trade_journal')


class NftCollectionsIndex(Base):
    __tablename__ = "nft_collections_index"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="nft_collections_index_pkey"),
        UniqueConstraint("collection_address", name="uq_nft_collections_index_address"),
        Index("ix_nft_collections_index_name_norm", "collection_name_normalized"),
        Index("ix_nft_collections_index_status", "index_status"),
        Index("ix_nft_collections_index_last_seen", "last_seen_at"),
        Index("ix_nft_collections_index_indexed_at", "indexed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    collection_address: Mapped[str] = mapped_column(String(128), nullable=False)
    collection_name: Mapped[Optional[str]] = mapped_column(Text)
    collection_name_normalized: Mapped[Optional[str]] = mapped_column(Text)
    owner_address: Mapped[Optional[str]] = mapped_column(String(128))
    next_item_index: Mapped[Optional[int]] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'tonapi'"))
    index_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'new'"))
    items_indexed_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    last_index_offset: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    indexed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class NftCollectionAliases(Base):
    __tablename__ = "nft_collection_aliases"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="nft_collection_aliases_pkey"),
        UniqueConstraint("alias_normalized", "collection_address", name="uq_nft_alias_norm_coll"),
        Index("ix_nft_collection_aliases_alias_norm", "alias_normalized"),
        Index("ix_nft_collection_aliases_coll_addr", "collection_address"),
        Index("ix_nft_collection_aliases_confidence", "confidence"),
        Index("ix_nft_collection_aliases_seen_count", "seen_count"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alias_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    collection_address: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'medium'"))
    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class NftItemsIndex(Base):
    __tablename__ = "nft_items_index"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="nft_items_index_pkey"),
        UniqueConstraint("nft_address", name="uq_nft_items_index_address"),
        Index("ix_nft_items_base_norm_num", "base_name_normalized", "item_number"),
        Index("ix_nft_items_coll_num", "collection_address", "item_number"),
        Index("ix_nft_items_coll_idx", "collection_address", "item_index"),
        Index("ix_nft_items_name_norm", "item_name_normalized"),
        Index("ix_nft_items_last_seen", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nft_address: Mapped[str] = mapped_column(String(128), nullable=False)
    collection_address: Mapped[str] = mapped_column(String(128), nullable=False)
    item_index: Mapped[Optional[int]] = mapped_column(BigInteger)
    item_number: Mapped[Optional[int]] = mapped_column(BigInteger)
    item_name: Mapped[Optional[str]] = mapped_column(Text)
    item_name_normalized: Mapped[Optional[str]] = mapped_column(Text)
    base_name: Mapped[Optional[str]] = mapped_column(Text)
    base_name_normalized: Mapped[Optional[str]] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    indexed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class NftIndexJobs(Base):
    __tablename__ = "nft_index_jobs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="nft_index_jobs_pkey"),
        Index("ix_nft_index_jobs_type", "job_type"),
        Index("ix_nft_index_jobs_status", "status"),
        Index("ix_nft_index_jobs_coll", "collection_address"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    collection_address: Mapped[Optional[str]] = mapped_column(String(128))
    offset_value: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1000"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
