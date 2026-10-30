import struct
import uuid
import zlib
from collections.abc import Sequence
from pathlib import Path

from mangadock_providers.image_base import ImageProvider, ImageResult


def make_png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\x2d\x6a\x47" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(
        b"IDAT", zlib.compress(rows)
    ) + chunk(b"IEND", b"")


class MockImageProvider(ImageProvider):
    def __init__(self, output_dir: str, workflow_id: str = "mock_v1") -> None:
        self._output_dir = Path(output_dir)
        self._workflow_id = workflow_id

    async def generate(
        self,
        prompt: str,
        reference_images: Sequence[str],
        size: tuple[int, int],
    ) -> ImageResult:
        width, height = size
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"{uuid.uuid4().hex}.png"
        path.write_bytes(make_png(width, height))
        return ImageResult(
            path=path,
            width=width,
            height=height,
            format="png",
            workflow_id=self._workflow_id,
            metadata={"mock": True},
        )
