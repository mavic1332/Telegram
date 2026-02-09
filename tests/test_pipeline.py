import pytest

from app.pipeline import Pipeline


@pytest.mark.asyncio
async def test_pipeline_mock_mode():
    p = Pipeline()
    states = []

    async def cb(msg: str):
        states.append(msg)

    result = await p.run("@ciao1234", "Telegram", cb)
    assert states == ["Search… 25%", "Search… 75%"]
    assert result.canonical_id.startswith("CID-")
    assert result.search_type == "Telegram"
