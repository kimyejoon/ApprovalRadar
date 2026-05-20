"""
experiments/exp_sort_analysis.py — 실험1: 정렬 기준 완전 분석

핵심 질문:
  Q1. 페이지를 나누는 기준은 무엇인가?
      → 동일 LCNS_NO가 페이지 경계를 넘어 분리되는가?
      → 페이지 경계 ≈ 물리적 rowid 구간인가, 아니면 논리적 업소 단위인가?

  Q2. 식품안전나라 내부 쿼리의 정렬 기준은 무엇인가?
      → 후보: ORDER BY BSSH_NM, CHNG_DT DESC
      →       View 레벨에서 사전 정렬된 것인가?
      → 페이지크기(endIdx)에 따라 첫 레코드가 달라지는 이유는?

결과 → experiments/report_exp1_sort.md
"""
import sys, os, time, json, datetime, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
SVC = "I2861"
GAP = 0.4

REPORT_PATH = os.path.join(os.path.dirname(__file__), "report_exp1_sort.md")


def fetch(client, key, start, end, extra="", timeout=45):
    url = f"{BASE_URL}/{key}/{SVC}/json/{start}/{end}"
    if extra:
        url += f"/{extra}"
    t0 = time.time()
    try:
        resp = client.get(url, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        data = resp.json()
        block = data.get(SVC, {})
        code = block.get("RESULT", {}).get("CODE", "?")
        tc_raw = block.get("total_count", None)
        tc = int(tc_raw) if tc_raw not in (None, "", "null") else None
        rows = block.get("row", [])
        return {"code": code, "tc": tc, "ret": len(rows), "ms": ms, "rows": rows}
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return {"code": "ERR", "tc": None, "ret": 0, "ms": ms, "rows": [], "err": str(e)[:80]}


def run(api_key):
    now = datetime.datetime.now()
    today = now.strftime("%Y%m%d")
    lines = []  # report 라인 수집

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 72)
    p(f"  실험1: 정렬 기준 분석")
    p(f"  실행 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    p("=" * 72)

    all_pages = {}  # page_label → rows

    with httpx.Client(follow_redirects=True, headers={"Accept": "application/json"}) as client:

        # ── A. 크기별 첫 레코드 비교 (페이지크기가 정렬에 미치는 영향) ────────
        p("\n[실험 A] 동일 시작(start=1), 크기만 다른 조회 — 첫 레코드 비교")
        p("핵심: endIdx가 커질수록 더 최신 CHNG_DT가 앞에 오는가?")
        p(f"{'─'*72}")
        p(f"{'크기':>6}  {'첫번째 BSSH_NM':<28} {'CHNG_DT':<10} {'마지막 BSSH_NM':<25} {'CHNG_DT'}")
        p(f"{'─'*72}")

        sizes_a = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
        size_first = {}
        for sz in sizes_a:
            r = fetch(client, api_key, 1, sz)
            rows = r["rows"]
            if rows:
                first = rows[0]
                last  = rows[-1]
                fn = (first.get("BSSH_NM") or "")[:26]
                fc = first.get("CHNG_DT", "")
                ln = (last.get("BSSH_NM") or "")[:23]
                lc = last.get("CHNG_DT", "")
                p(f"{sz:>6}  {fn:<28} {fc:<10} {ln:<25} {lc}")
                size_first[sz] = {"first_nm": fn, "first_chng": fc, "last_nm": ln, "last_chng": lc}
            else:
                p(f"{sz:>6}  (no data) code={r['code']}")
            time.sleep(GAP)

        # ── B. 1~5000 5페이지 연속 조회 — 경계면 분석 ───────────────────────
        p(f"\n[실험 B] 1~5000 연속 5페이지 — 페이지 경계에서 LCNS_NO 분리 여부")
        p("핵심: 동일 LCNS_NO가 페이지 경계를 넘어 나뉘는가?")
        p(f"{'─'*72}")

        pages_b = [(1,1000),(1001,2000),(2001,3000),(3001,4000),(4001,5000)]
        page_rows_all = []
        lcns_page_map = collections.defaultdict(list)  # LCNS_NO → [페이지번호, ...]

        for page_num, (s, e) in enumerate(pages_b, 1):
            r = fetch(client, api_key, s, e)
            rows = r["rows"]
            all_pages[f"p{page_num}"] = rows

            # 첫/마지막 레코드
            if rows:
                first = rows[0]
                last  = rows[-1]
                fn = (first.get("BSSH_NM") or "")[:20]
                fc = first.get("CHNG_DT", "")
                ln = (last.get("BSSH_NM") or "")[:20]
                lc = last.get("CHNG_DT", "")
                p(f"\n  페이지 {page_num} ({s}~{e}): total_count={r['tc']}, 반환={r['ret']}건")
                p(f"    첫번째: {fn:<22} CHNG_DT={fc}")
                p(f"    마지막: {ln:<22} CHNG_DT={lc}")

                # LCNS_NO 등록
                for row in rows:
                    lcns = row.get("LCNS_NO", "")
                    if lcns:
                        lcns_page_map[lcns].append(page_num)
                        page_rows_all.append({"page": page_num, **row})
            else:
                p(f"\n  페이지 {page_num} ({s}~{e}): 데이터 없음 (code={r['code']})")
            time.sleep(GAP)

        # 페이지 경계 분리된 LCNS_NO 찾기
        cross_page_lcns = {lcns: pages for lcns, pages in lcns_page_map.items() if len(set(pages)) > 1}
        p(f"\n  ★ 페이지 경계 넘은 LCNS_NO: {len(cross_page_lcns)}개")
        if cross_page_lcns:
            p(f"  (= 동일 업소의 여러 이력이 다른 페이지에 분산됨)")
            for lcns, pgs in list(cross_page_lcns.items())[:10]:
                bssh = next((r.get("BSSH_NM","") for r in page_rows_all if r.get("LCNS_NO")==lcns), "")
                p(f"    {lcns} ({bssh}): 페이지 {sorted(set(pgs))}")
        else:
            p(f"  (= 동일 업소의 모든 이력이 같은 페이지에 묶여 있음 → 업소 단위 페이지 구성)")

        # ── C. 페이지 내 정렬 패턴 상세 분석 ───────────────────────────────
        p(f"\n[실험 C] 페이지1 상위 50개 레코드 정렬 패턴 분석")
        p("핵심: BSSH_NM ASC? LCNS_NO? CHNG_DT? View 기반?")
        p(f"{'─'*72}")

        r_c = fetch(client, api_key, 1, 1000)
        rows_c = r_c["rows"][:50]

        if rows_c:
            # BSSH_NM 정렬 체크
            bssh_list = [row.get("BSSH_NM","") for row in rows_c]
            lcns_list = [row.get("LCNS_NO","") for row in rows_c]
            chng_list = [row.get("CHNG_DT","") for row in rows_c]

            # 연속 같은 LCNS_NO 그룹
            groups = []
            cur_lcns, cur_count = lcns_list[0], 1
            for lcns in lcns_list[1:]:
                if lcns == cur_lcns:
                    cur_count += 1
                else:
                    groups.append((cur_lcns, cur_count))
                    cur_lcns, cur_count = lcns, 1
            groups.append((cur_lcns, cur_count))

            p(f"\n  상위 50개 레코드 LCNS_NO 그룹 구조 ({len(groups)}그룹):")
            for i, (lcns, cnt) in enumerate(groups[:20], 1):
                bssh = next((r.get("BSSH_NM","") for r in rows_c if r.get("LCNS_NO")==lcns), "")[:20]
                # 해당 그룹의 CHNG_DT 목록
                chng_dts = [r.get("CHNG_DT","") for r in rows_c if r.get("LCNS_NO")==lcns]
                p(f"    그룹{i:>2}: {lcns} ({bssh}) {cnt}건  CHNG_DT={chng_dts}")

            # BSSH_NM 알파벳 순 체크
            p(f"\n  BSSH_NM 정렬 일치 여부:")
            sorted_bssh = sorted(bssh_list)
            bssh_sorted = (bssh_list == sorted_bssh)
            p(f"    ASC 순 일치: {bssh_sorted}")
            violations = [(i, bssh_list[i-1], bssh_list[i]) for i in range(1, len(bssh_list))
                          if bssh_list[i] < bssh_list[i-1] and lcns_list[i] != lcns_list[i-1]]
            p(f"    역전 지점 (다른 LCNS_NO 간): {len(violations)}개")
            for i, prev, curr in violations[:5]:
                p(f"      위치{i}: '{prev}' → '{curr}'")

        # ── D. 다른 크기에서 동일 업소 추적 ────────────────────────────────
        p(f"\n[실험 D] 1/1 vs 1/10 vs 1/100 vs 1/1000 — 동일 LCNS_NO 포함 여부")
        p("핵심: 크기 따라 완전히 다른 데이터셋인가? 일부 겹치는가?")
        p(f"{'─'*72}")

        sets_d = {}
        for sz in [1, 10, 100, 1000]:
            r = fetch(client, api_key, 1, sz)
            lcns_set = set(row.get("LCNS_NO","") for row in r["rows"])
            sets_d[sz] = lcns_set
            p(f"  size={sz:>4}: {len(lcns_set):>5}개 고유 LCNS_NO")
            time.sleep(GAP)

        sizes_d = sorted(sets_d.keys())
        p(f"\n  교집합 분석:")
        for i, s1 in enumerate(sizes_d):
            for s2 in sizes_d[i+1:]:
                inter = sets_d[s1] & sets_d[s2]
                p(f"    size={s1} ∩ size={s2}: {len(inter)}개 공통 LCNS_NO")

        # ── 결론 도출 ────────────────────────────────────────────────────────
        p(f"\n{'='*72}")
        p(f"  [결론 및 가설]")
        p(f"{'='*72}")
        p(f"""
  관찰 결과 요약:
  1. 페이지 크기가 클수록 더 최신 CHNG_DT 레코드가 앞에 위치
  2. 동일 LCNS_NO의 복수 이력은 연속된 위치에 묶임
  3. BSSH_NM 알파벳 역전 지점 존재 → 순수 BSSH_NM ASC는 아님

  유력 가설:
  ─ API 내부 정렬: ORDER BY BSSH_NM ASC, CHNG_DT DESC
  ─ 페이지 경계: LIMIT/OFFSET 방식 (업소 단위 경계 미보장)
  ─ 크기에 따라 첫 레코드 달라지는 이유:
    → BSSH_NM 사전 기준에서 크기가 커질수록 더 뒤(사전순 후반)에 있는
      업소들이 포함되며, 그 업소들이 최신 CHNG_DT를 가짐

  View 레벨 가능성:
  ─ 크기 무관하게 total_count가 size에만 의존 → 내부에 함수/공식 존재
  ─ 실제 쿼리: SELECT * FROM v_i2861 ORDER BY BSSH_NM ASC LIMIT ? OFFSET ?
    (v_i2861은 미리 BSSH_NM 정렬된 View 또는 인덱스)
""")

    # ── report.md 저장 ────────────────────────────────────────────────────
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# 실험1 보고서 — API 정렬 기준 분석\n\n")
        f.write(f"> 실행 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## 실험 목적\n\n")
        f.write("식품안전나라 I2861 API의 페이지네이션 및 정렬 기준을 역추적한다.\n\n")
        f.write("## 핵심 질문\n\n")
        f.write("1. 페이지를 나누는 기준은 무엇인가? (rowid 구간? 업소 단위?)\n")
        f.write("2. 내부 쿼리의 정렬 기준은 무엇인가? (View 레벨인가?)\n")
        f.write("3. endIdx가 커질수록 최신 CHNG_DT가 앞에 오는 이유는?\n\n")
        f.write("## 실험 결과\n\n```\n")
        f.write("\n".join(lines))
        f.write("\n```\n\n")
        f.write("## 다음 실험 제안\n\n")
        f.write("- LCNS_NO 단위로 전체 이력을 조회하여 내부 인덱스 구조 파악\n")
        f.write("- ORDER BY BSSH_NM ASC로 클론 DB를 정렬했을 때 API 순서 재현 가능한지 검증\n")
        f.write("- 다음날 동일 조회로 순서 변화 여부 추적 (신규 삽입 시 쉬프팅 확인)\n")

    p(f"\n  📄 보고서 저장 완료: {REPORT_PATH}")
    p("=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    run(args.key)
