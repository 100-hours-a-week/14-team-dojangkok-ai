from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from app.api.schemas.checklist import ChecklistRequest, ChecklistAcceptedResponse
from app.api.deps import get_container

router = APIRouter(prefix="/api/checklists", tags=["checklists"])


async def _run_checklist_and_callback(container, case_id: str, keywords: list[str]):
    try:
        checklists = await container.checklist_service.generate(case_id, keywords)
        await container.callback.post_checklist_complete(case_id, {"checklists": checklists})
    except Exception:
        try:
            await container.callback.post_checklist_complete(
                case_id,
                {"error": {"code": "failed", "message": "체크리스트 생성 중 오류가 발생하였습니다."}},
            )
        except Exception:
            pass


@router.post("/{id}", response_model=ChecklistAcceptedResponse)
def create_checklists(
    body: ChecklistRequest,
    background_tasks: BackgroundTasks,
    id: str = Path(..., description="케이스 식별자"),
    container=Depends(get_container),
):
    keywords = body.keywords or []
    if not isinstance(keywords, list) or any(not isinstance(x, str) for x in keywords):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_INPUT", "message": "keywords는 문자열 배열이어야 합니다."}},
        )

    background_tasks.add_task(_run_checklist_and_callback, container, id, keywords)
    return ChecklistAcceptedResponse(id=id, message="요청이 접수되었습니다.")
