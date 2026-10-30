import struct

import pytest

from mangadock_providers import MockImageProvider


@pytest.mark.asyncio
async def test_mock_image_provider_returns_local_png_and_metadata(tmp_path) -> None:
    provider = MockImageProvider(output_dir=str(tmp_path), workflow_id="mock_v1")

    result = await provider.generate("角色正面全身", [], (32, 16))

    content = result.path.read_bytes()
    assert result.path.exists()
    assert result.path.suffix == ".png"
    assert result.width == 32
    assert result.height == 16
    assert result.format == "png"
    assert result.workflow_id == "mock_v1"
    assert result.metadata["mock"] is True
    assert struct.unpack(">II", content[16:24]) == (32, 16)
