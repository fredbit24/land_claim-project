import hashlib
import json
from datetime import datetime, timezone

from django.db import transaction
from .models import AuditBlock

GENESIS_PREVIOUS_HASH = "0" * 64


def _canonical_hash(index, timestamp, event_type, payload, previous_hash):
    body = {
        "index": index,
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": payload,
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _create_genesis():
    existing = AuditBlock.objects.filter(block_index=0).first()
    if existing:
        return existing
    timestamp = datetime.now(timezone.utc)
    payload = {"message": "Landclaim audit ledger initialized"}
    return AuditBlock.objects.create(
        block_index=0, timestamp=timestamp, event_type="genesis", payload=payload,
        previous_hash=GENESIS_PREVIOUS_HASH,
        hash=_canonical_hash(0, timestamp, "genesis", payload, GENESIS_PREVIOUS_HASH),
    )


def append_audit_event(event_type, payload):
    """Server-only append operation; clients never provide hashes."""
    with transaction.atomic():
        latest = AuditBlock.objects.select_for_update().order_by("-block_index").first() or _create_genesis()
        timestamp = datetime.now(timezone.utc)
        index = latest.block_index + 1
        digest = _canonical_hash(index, timestamp, event_type, payload, latest.hash)
        return AuditBlock.objects.create(
            block_index=index, timestamp=timestamp, event_type=event_type,
            payload=payload, previous_hash=latest.hash, hash=digest,
        )


def validate_chain():
    blocks = list(AuditBlock.objects.order_by("block_index"))
    if not blocks:
        return {"valid": True, "length": 0, "detail": "Ledger has not been initialized."}
    expected_previous = GENESIS_PREVIOUS_HASH
    for expected_index, block in enumerate(blocks):
        if block.block_index != expected_index:
            return {"valid": False, "length": len(blocks), "invalid_block": block.block_index, "detail": "Block indexes are not continuous."}
        calculated = _canonical_hash(block.block_index, block.timestamp, block.event_type, block.payload, block.previous_hash)
        if block.previous_hash != expected_previous or block.hash != calculated:
            return {"valid": False, "length": len(blocks), "invalid_block": block.block_index, "detail": "Hash linkage or block contents were modified."}
        expected_previous = block.hash
    return {"valid": True, "length": len(blocks), "latest_hash": expected_previous}