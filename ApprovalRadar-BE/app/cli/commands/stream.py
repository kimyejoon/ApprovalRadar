def test_stream_update():
    print("가상의 SSE 업데이트 이벤트를 트리거합니다...")
    try:
        import requests
        response = requests.post("http://localhost:8000/api/v1/stream/test-trigger")
        if response.status_code == 200:
            print("✅ SSE 이벤트 브로드캐스트 트리거 성공!")
        else:
            print(f"❌ 트리거 실패 (Status: {response.status_code})")
    except Exception as e:
        print(f"❌ 요청 중 오류 발생: {e}\n(서버가 http://localhost:8000 에서 켜져있는지 확인해주세요)")
