from app.db.repositories.audit import AuditLogRepository


async def log_audit(
    session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata_json: dict | None = None,
) -> None:
    await AuditLogRepository(session).create(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata_json,
    )
