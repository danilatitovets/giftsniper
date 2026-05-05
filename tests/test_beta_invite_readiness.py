from app.services.beta_invite_readiness import BetaInviteReadiness


def test_invite_readiness_dataclass_fields():
    r = BetaInviteReadiness(
        active_rows=1,
        valid_active_invites=1,
        expired_still_flagged_active=0,
        remaining_redemptions_capacity=3,
        total_redemptions_all_time=0,
        require_invite_gate=True,
        blocking_no_valid_invite=False,
    )
    assert r.valid_active_invites == 1
    assert r.blocking_no_valid_invite is False
