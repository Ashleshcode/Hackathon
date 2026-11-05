"""TEST-ONLY detector and store. Nothing under ``app/`` may import this file.

The mock replays a fixed script and never generates random scores. Its
``is_test_only_mock`` flag makes production wiring refuse it, and makes any
result it produces carry a warning saying so.
"""

from pathlib import Path

from app.media.interfaces import (
    DetectionResult,
    MediaFetchError,
    ModelInfo,
    StoredMedia,
)

FACE_FAKE = DetectionResult(1, "fake", 2.5)
FACE_REAL = DetectionResult(1, "real", -1.5)
FACE_UNCERTAIN = DetectionResult(1, "uncertain", None)
NO_FACE = DetectionResult(0, "unsupported", None)


class ScriptedMockDetector:
    """Returns scripted results in order, repeating the last one."""

    is_test_only_mock = True
    model_info = ModelInfo("TEST_ONLY_MOCK", "TEST_ONLY_MOCK", "TEST_ONLY_MOCK")

    def __init__(self, script: list[DetectionResult]) -> None:
        self.script = script
        self.calls = 0

    def analyze_image(self, image: object) -> DetectionResult:
        result = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return result


class RaisingMockDetector(ScriptedMockDetector):
    def __init__(self) -> None:
        super().__init__([])

    def analyze_image(self, image: object) -> DetectionResult:
        raise RuntimeError("CUDA out of memory")


class FakeMediaStore:
    """Maps media IDs to records and local files."""

    def __init__(self) -> None:
        self.records: dict[str, tuple[StoredMedia, Path | None]] = {}

    def add(
        self,
        media_id: str,
        media_type: str,
        path: Path | None,
        mime_type: str | None = None,
    ) -> None:
        media = StoredMedia(media_id, "post_0001", "mon_0001", media_type, mime_type)
        self.records[media_id] = (media, path)

    def get_media(self, media_id: str) -> StoredMedia | None:
        record = self.records.get(media_id)
        return record[0] if record else None

    def get_local_path(self, media: StoredMedia) -> Path:
        path = self.records[media.media_id][1]
        if path is None:
            raise MediaFetchError("Could not download media from the platform")
        return path
