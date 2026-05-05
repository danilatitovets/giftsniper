def clamp_reason_lines(reasons: list[str], limit: int = 4) -> str:
    return "\n".join(f"- {line}" for line in reasons[:limit])
