from __future__ import annotations

import time


class CancelRegistry:
    def __init__(self, ttl_sec: int) -> None:
        self._ttl_sec = ttl_sec
        self._expiry_by_job_id: dict[str, float] = {}

    def mark_cancelled(self, job_id: str) -> None:
        if not job_id:
            return
        self._expiry_by_job_id[job_id] = time.time() + self._ttl_sec

    def is_cancelled(self, job_id: str) -> bool:
        if not job_id:
            return False
        expiry = self._expiry_by_job_id.get(job_id)
        if expiry is None:
            return False
        if expiry < time.time():
            self._expiry_by_job_id.pop(job_id, None)
            return False
        return True

    def cleanup_expired(self) -> None:
        now = time.time()
        expired_keys = [job_id for job_id, expiry in self._expiry_by_job_id.items() if expiry < now]
        for job_id in expired_keys:
            self._expiry_by_job_id.pop(job_id, None)
