def run_backfill():
    print("DB에 누락된 세부업종 데이터를 단건 조회를 통해 채워넣습니다(Backfill)...")
    from app.services.industry_filler import fill_missing_industry_types
    fill_missing_industry_types()
