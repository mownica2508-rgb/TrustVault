"""HMAC-sealed audit events with a serialized database checkpoint."""

import hashlib
import hmac
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.audit import AuditChainState, AuditEvent

GENESIS_HASH = hashlib.sha256(b"trustvault:audit-chain:v1").hexdigest()


def _signing_key() -> bytes:
    settings = get_settings()
    if settings.audit_hmac_key is not None:
        return settings.audit_hmac_key.get_secret_value().encode("utf-8")
    # Backwards-compatible local setup. Deployments should set a dedicated key.
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode("utf-8"),
        b"trustvault:audit-hmac-key:v1",
        hashlib.sha256,
    ).digest()


def _canonical_event(event: AuditEvent) -> bytes:
    created_at = event.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    fields = {
        "id": event.id,
        "actor_id": event.actor_id,
        "document_id": event.document_id,
        "action": event.action,
        "outcome": event.outcome,
        "details": event.details,
        "created_at": created_at.replace(microsecond=0).isoformat(),
        "previous_hash": event.previous_hash,
    }
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _event_digest(event: AuditEvent) -> str:
    return hmac.new(_signing_key(), _canonical_event(event), hashlib.sha256).hexdigest()


def append_audit(
    db: Session,
    actor_id: int | None,
    action: str,
    outcome: str,
    document_id: int | None = None,
    **details: object,
) -> AuditEvent:
    """Append and seal one event in the same transaction as the caller's work."""
    state = db.scalar(
        select(AuditChainState).where(AuditChainState.id == 1).with_for_update()
    )
    if state is None:
        state = AuditChainState(
            id=1,
            last_event_id=None,
            last_hash=GENESIS_HASH,
            legacy_through_id=0,
            legacy_event_count=0,
        )
        db.add(state)
        db.flush()

    serialized_details = (
        json.dumps(details, sort_keys=True, separators=(",", ":"), default=str)
        if details
        else None
    )
    event = AuditEvent(
        actor_id=actor_id,
        document_id=document_id,
        action=action,
        outcome=outcome,
        details=serialized_details,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
        previous_hash=state.last_hash,
    )
    db.add(event)
    db.flush()
    event.event_hash = _event_digest(event)
    state.last_event_id = event.id
    state.last_hash = event.event_hash
    db.flush()
    return event


def verify_audit_chain(db: Session) -> dict[str, int | bool]:
    """Check HMACs, ordering, and the stored checkpoint without exposing event data."""
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    state = db.get(AuditChainState, 1)
    expected_previous = GENESIS_HASH
    sealed_count = 0
    unsealed_count = 0
    valid = True
    chain_started = False
    last_sealed_id: int | None = None

    for event in events:
        if event.event_hash is None or event.previous_hash is None:
            unsealed_count += 1
            # Only the legacy prefix may be unsealed. A new unsealed row after
            # HMAC records begin indicates a bypass of the audit writer.
            legacy_prefix = state.legacy_through_id if state is not None else 0
            if chain_started or event.id > legacy_prefix:
                valid = False
            continue
        chain_started = True
        if event.previous_hash != expected_previous or not hmac.compare_digest(
            event.event_hash, _event_digest(event)
        ):
            valid = False
        expected_previous = event.event_hash
        last_sealed_id = event.id
        sealed_count += 1

    if state is not None and unsealed_count != state.legacy_event_count:
        valid = False
    checkpoint_matches = (
        state is not None
        and state.last_hash == expected_previous
        and state.last_event_id == last_sealed_id
    )
    if state is None and sealed_count == 0:
        checkpoint_matches = True
    return {
        "valid": valid and checkpoint_matches,
        "checkpoint_matches": checkpoint_matches,
        "sealed_events": sealed_count,
        "legacy_unsealed_events": unsealed_count,
    }
