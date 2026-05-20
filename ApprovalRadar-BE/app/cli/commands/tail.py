import asyncio

def test_tail():
    print("현재 데이터의 꼬리(Tail) 지점을 조회합니다...\n")

    async def _run():
        from app.repositories.state_repository import StateRepository
        from app.core.config import settings as _s
        state_repo = StateRepository()

        services = getattr(_s, "SERVICES", ["I2861"])
        svc_names = {"I2861": "음식점업소"}

        for service_id in services:
            svc_name = svc_names.get(service_id, service_id)
            print(f"\n{'─' * 50}")
            print(f"📡 [{service_id}] {svc_name}")
            print(f"{'─' * 50}")

            state = state_repo.load_state(service_id)
            db_tail = state.get("last_total_count", 0)
            print(f"  📋 DB 저장 tail: {db_tail:,}건")
            print("  💡 (이진탐색/Tail Ping 최적화 제거로 실시간 이진탐색은 지원하지 않습니다)")

    asyncio.run(_run())
    print(f"\n{'─' * 50}")
    print("✅ 조회 완료")
