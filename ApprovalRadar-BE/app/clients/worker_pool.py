"""
ApiWorkerPool — 살아있는 API 키 기반 ApiClient 워커 풀.

소진 키를 제외한 alive 키를 n_workers개 클라이언트에 균등 배분합니다.
동일 키에 여러 워커가 몰리는 WAF 동시 차단을 구조적으로 방지합니다.

사용 예시:
    pool = ApiWorkerPool(settings.SCAN_WORKERS, label="I2861")
    semaphore = pool.semaphore
    client    = pool.get_client(worker_id - 1)   # 0-based task index
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core.logger import logger

if TYPE_CHECKING:
    from app.clients.foodsafety_api import ApiClient


class ApiWorkerPool:
    """
    살아있는 API 키 기반 ApiClient 풀.

    Attributes:
        n_workers: 실제 활성 워커 수 (min(requested, alive_keys)).
        n_alive:   풀 생성 시점의 살아있는 키 수.
        semaphore: asyncio.Semaphore (lazy 초기화, 이벤트 루프 안전).
    """

    def __init__(self, n_workers: int, label: str = "") -> None:
        """
        Args:
            n_workers: 요청 워커 수. 살아있는 키 수로 자동 상한 제한.
            label:     로그 접두어 (예: "I2861", "CHNG_DT Poller").
                       빈 문자열이면 키 배분 로그를 출력하지 않음.
        """
        from app.clients.foodsafety_api import ApiClient
        from app.clients.key_manager import KeyManager
        from app.core.config import settings

        all_keys = settings.API_KEYS

        # ── 살아있는 키 인덱스 추출 ────────────────────────────────────────
        alive_indices = [
            i for i, k in enumerate(all_keys)
            if k not in KeyManager._exhausted_keys
        ]
        base_indices = alive_indices if alive_indices else list(range(len(all_keys)))

        # ── 워커 수 클램핑: 살아있는 키 수 초과 금지 (WAF 차단 방지) ──────
        eff = min(n_workers, len(base_indices)) if base_indices else 1
        if eff < n_workers and label:
            logger.warning(
                f"[{label}] ⚠️ 살아있는 키 {len(base_indices)}개 → "
                f"워커 수 {n_workers} → {eff}으로 축소 (WAF 차단 방지)"
            )

        # ── ApiClient 생성 + 시작 키 균등 배분 ──────────────────────────
        key_step = max(1, len(base_indices) // eff)
        self._clients: list[ApiClient] = [ApiClient() for _ in range(eff)]
        for i, client in enumerate(self._clients):
            assigned_idx = base_indices[(i * key_step) % len(base_indices)]
            client.key_manager.current_key_idx = assigned_idx
            if label:
                masked = client.key_manager._mask_key(all_keys[assigned_idx])
                logger.info(
                    f"[{label}] 🔑 W{i + 1} 시작 키: {masked} "
                    f"(key_idx={assigned_idx}, 살아있는 키 {len(base_indices)}/{len(all_keys)}개 중)"
                )

        self._n_workers = eff
        self._n_alive   = len(base_indices)
        self._semaphore: asyncio.Semaphore | None = None

    # ── Public API ──────────────────────────────────────────────────────

    def get_client(self, task_idx: int) -> ApiClient:
        """
        0-based task_idx를 round-robin으로 워커 클라이언트에 매핑.

        Args:
            task_idx: 0-based 태스크 인덱스 (음수 허용: Python 모듈로 시맨틱).

        Returns:
            해당 워커의 ApiClient 인스턴스.
        """
        return self._clients[task_idx % self._n_workers]

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """Lazy 초기화 — 실행 중인 이벤트 루프 컨텍스트에서 안전하게 생성."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._n_workers)
        return self._semaphore

    @property
    def n_workers(self) -> int:
        """실제 활성 워커 수."""
        return self._n_workers

    @property
    def n_alive(self) -> int:
        """풀 생성 시점의 살아있는 키 수."""
        return self._n_alive
