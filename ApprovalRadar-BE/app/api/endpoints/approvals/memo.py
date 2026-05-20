from fastapi import APIRouter, HTTPException, Query, Depends
from app.core.logger import logger
from app.schemas.approvals import MemoResponse, MemoCreateRequest, MemoUpdateRequest

router = APIRouter()

def get_memo_repo():
    from app.repositories.memo_repository import MemoRepository
    return MemoRepository()

@router.get("/memo", response_model=MemoResponse, summary="메모 조회")
def get_memo(
    license_date: str = Query(..., description="최초인허가일 (YYYYMMDD)"),
    business_name: str = Query(..., description="상호명"),
    repo=Depends(get_memo_repo)
):
    """해당 건의 메모를 반환합니다. 메모가 없으면 data=null을 반환합니다."""
    try:
        memo = repo.get_memo(license_date, business_name)
        return {"status": "success", "data": memo}
    except Exception as e:
        logger.error(f"Error in get_memo: {e}")
        raise HTTPException(status_code=500, detail="메모 조회 중 오류가 발생했습니다.")


@router.post("/memo", response_model=MemoResponse, summary="메모 생성", status_code=201)
def create_memo(
    body: MemoCreateRequest,
    repo=Depends(get_memo_repo)
):
    """해당 건의 메모를 생성합니다. 이미 메모가 존재하면 409를 반환합니다."""
    try:
        memo = repo.create_memo(body.license_date, body.business_name, body.content)
        return {"status": "success", "data": memo}
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "constraint" in err_str:
            raise HTTPException(status_code=409, detail="이미 메모가 존재합니다. 수정을 이용해주세요.")
        logger.error(f"Error in create_memo: {e}")
        raise HTTPException(status_code=500, detail="메모 생성 중 오류가 발생했습니다.")


@router.put("/memo", response_model=MemoResponse, summary="메모 수정")
def update_memo(
    body: MemoUpdateRequest,
    repo=Depends(get_memo_repo)
):
    """해당 건의 메모를 수정합니다. 메모가 없으면 404를 반환합니다."""
    try:
        memo = repo.update_memo(body.license_date, body.business_name, body.content)
        if memo is None:
            raise HTTPException(status_code=404, detail="수정할 메모를 찾을 수 없습니다.")
        return {"status": "success", "data": memo}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_memo: {e}")
        raise HTTPException(status_code=500, detail="메모 수정 중 오류가 발생했습니다.")


@router.delete("/memo", summary="메모 삭제", status_code=200)
def delete_memo(
    license_date: str = Query(..., description="최초인허가일 (YYYYMMDD)"),
    business_name: str = Query(..., description="상호명"),
    repo=Depends(get_memo_repo)
):
    """해당 건의 메모를 삭제합니다. 메모가 없으면 404를 반환합니다."""
    try:
        deleted = repo.delete_memo(license_date, business_name)
        if not deleted:
            raise HTTPException(status_code=404, detail="삭제할 메모를 찾을 수 없습니다.")
        return {"status": "success", "message": "메모가 삭제되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_memo: {e}")
        raise HTTPException(status_code=500, detail="메모 삭제 중 오류가 발생했습니다.")
