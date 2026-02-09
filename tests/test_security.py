import time

from app.security import RateLimiter, mask_identifier


def test_mask_identifier():
    assert mask_identifier("+393331234567").startswith("+3")
    assert "3331234567" not in mask_identifier("+393331234567")


def test_rate_limit():
    rl = RateLimiter(cooldown_seconds=1)
    assert rl.allow(1)
    assert not rl.allow(1)
    time.sleep(1.05)
    assert rl.allow(1)
