import asyncio
import base64
import logging
import time
from typing import AsyncIterator

from fastapi import UploadFile

from app.adapters.base import VisionProvider
from app.config import Settings
from app.constants import ALLOWED_MIME_TYPES, MAX_FILE_SIZE_BYTES
from app.models import ApplicationData, OverallStatus, VerificationResult
from app.prompts.verify_prompt import _make_needs_review_result

logger = logging.getLogger(__name__)


class VerificationService:
    def __init__(self, provider: VisionProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    async def verify_single(
        self,
        file: UploadFile,
        application_data: ApplicationData,
    ) -> VerificationResult:
        """Verify one label image against the provided application data."""
        start = time.monotonic()
        try:
            image_b64, mime_type = await _read_and_encode(file)
            result = await self.provider.verify_label(image_b64, mime_type, application_data)
        except ValueError as exc:
            note = str(exc)
            result = _make_needs_review_result(application_data, note)
        except Exception as exc:
            note = f"Unexpected error during verification: {exc}"
            logger.exception(note)
            result = _make_needs_review_result(application_data, note)

        result.processing_time_ms = (time.monotonic() - start) * 1000
        result.filename = file.filename
        return result

    async def verify_batch(
        self,
        files: list[UploadFile],
        application_data: ApplicationData,
    ) -> AsyncIterator[VerificationResult]:
        """Verify multiple labels concurrently, yielding each result as soon as
        its own task finishes — not after the whole batch completes.

        Concurrency is bounded by a semaphore derived from RATE_LIMIT_RPM so the
        batch doesn't exhaust the provider's per-minute quota all at once.
        """
        # Reserve at most 25% of the RPM budget for concurrent inflight calls
        max_concurrent = max(1, self.settings.RATE_LIMIT_RPM // 4)
        semaphore = asyncio.Semaphore(max_concurrent)

        results_queue: asyncio.Queue[VerificationResult | None] = asyncio.Queue()

        async def bounded_verify(f: UploadFile) -> None:
            # Each task enqueues its own result the moment it finishes, so
            # completions can be consumed as they arrive instead of waiting
            # for the slowest task in the batch.
            async with semaphore:
                try:
                    result = await self.verify_single(f, application_data)
                except Exception as exc:
                    # verify_single already catches its own errors internally;
                    # this is a backstop for anything unexpected that still
                    # escapes it, keeping one failure from blocking the rest.
                    note = f"Label verification failed: {exc}"
                    logger.warning(note)
                    result = _make_needs_review_result(application_data, note)
                    result.filename = f.filename
            await results_queue.put(result)

        async def run_all() -> None:
            tasks = [asyncio.create_task(bounded_verify(f)) for f in files]
            # return_exceptions=True means one failure doesn't cancel others;
            # each task already enqueued its own result/fallback above, so
            # this is only waiting to know when to push the sentinel.
            await asyncio.gather(*tasks, return_exceptions=True)
            await results_queue.put(None)  # sentinel

        asyncio.create_task(run_all())

        while True:
            result = await results_queue.get()
            if result is None:
                break
            yield result


async def _read_and_encode(file: UploadFile) -> tuple[str, str]:
    """Read upload, validate mime/size, return (base64_string, mime_type)."""
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported file type '{content_type}'. "
            f"Accepted: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )

    data = await file.read()
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File '{file.filename}' exceeds maximum size of "
            f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        )

    return base64.b64encode(data).decode("utf-8"), content_type
