# from __future__ import annotations

# from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, UploadFile
# from app.api.schemas.easy_contract import EasyContractAcceptedResponse
# from fastapi.responses import PlainTextResponse
# from app.api.deps import get_container

# router = APIRouter(prefix="/api/easycontract", tags=["easycontract"])

# ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}

# def _ext_ok(filename: str) -> bool:
#     f = (filename or "").lower()
#     return any(f.endswith(ext) for ext in ALLOWED_EXT)

# async def _run_easy_contract_and_callback(container, case_id: int, docs: list[dict]):
#     try:
#         md = await container.easy_contract_service.generate(case_id=case_id, docs=docs)
#         if not md.strip():
#             await container.callback.post_easy_contract_error(
#                 case_id, "failed", "쉬운 계약서 생성 중 오류가 발생하였습니다."
#             )
#             return
#         await container.callback.post_easy_contract_markdown(case_id, md)
#     except RuntimeError as e:
#         if str(e) == "UNPROCESSABLE_DOCUMENT":
#             await container.callback.post_easy_contract_error(
#                 case_id,
#                 "UNPROCESSABLE_DOCUMENT",
#                 "문서를 처리할 수 없습니다. 파일이 손상되었거나 암호화되어 있을 수 있습니다.",
#             )
#         else:
#             await container.callback.post_easy_contract_error(
#                 case_id, "failed", "쉬운 계약서 생성 중 오류가 발생하였습니다."
#             )
#     except Exception:
#         await container.callback.post_easy_contract_error(
#             case_id, "failed", "쉬운 계약서 생성 중 오류가 발생하였습니다."
#         )

# @router.post("/{id}", response_model=EasyContractAcceptedResponse, status_code=202)
# async def create_easy_contract(
#     background_tasks: BackgroundTasks,
#     id: int = Path(..., description="쉬운계약서 식별자(int)"),
#     files: list[UploadFile] = File(..., description="pdf/png/jpg 최대 5개"),
#     doc_types: list[str] = Form(..., description="files와 같은 순서의 문서 타입"),
#     container=Depends(get_container),
# ):
#     if not files or len(files) < 1 or len(files) > 5:
#         raise HTTPException(
#             status_code=400,
#             detail={"error": {"code": "INVALID_INPUT", "message": "files는 1개 이상 5개 이하로 업로드해야 합니다."}},
#         )

#     if not doc_types or len(doc_types) != len(files):
#         raise HTTPException(
#             status_code=400,
#             detail={"error": {"code": "DOC_TYPES_MISMATCH", "message": "doc_types 길이는 files 길이와 같아야 합니다."}},
#         )

#     for f in files:
#         if not _ext_ok(f.filename or ""):
#             raise HTTPException(
#                 status_code=400,
#                 detail={"error": {"code": "UNSUPPORTED_FILE_TYPE", "message": "pdf/png/jpg 파일만 업로드할 수 있습니다."}},
#             )

#     docs: list[dict] = []
#     for f, dt in zip(files, doc_types):
#         b = await f.read()
#         if not b:
#             raise HTTPException(
#                 status_code=400,
#                 detail={"error": {"code": "INVALID_INPUT", "message": "비어있는 파일은 업로드할 수 없습니다."}},
#             )
#         docs.append({"filename": f.filename, "bytes": b, "doc_type": dt})

#     background_tasks.add_task(_run_easy_contract_and_callback, container, id, docs)

#     return EasyContractAcceptedResponse(id=id, message="요청이 접수되었습니다.")
# app/api/routers/easy_contract.py
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, UploadFile
from fastapi.responses import PlainTextResponse

from app.api.schemas.easy_contract import EasyContractAcceptedResponse
from app.api.deps import get_container

router = APIRouter(prefix="/api/easycontract", tags=["easycontract"])

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}


def _ext_ok(filename: str) -> bool:
    f = (filename or "").lower()
    return any(f.endswith(ext) for ext in ALLOWED_EXT)


def _validate_inputs(files: list[UploadFile], doc_types: list[str]) -> None:
    if not files or len(files) < 1 or len(files) > 5:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_INPUT", "message": "files는 1개 이상 5개 이하로 업로드해야 합니다."}},
        )

    if not doc_types or len(doc_types) != len(files):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "DOC_TYPES_MISMATCH", "message": "doc_types 길이는 files 길이와 같아야 합니다."}},
        )

    for f in files:
        if not _ext_ok(f.filename or ""):
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "UNSUPPORTED_FILE_TYPE", "message": "pdf/png/jpg 파일만 업로드할 수 있습니다."}},
            )


async def _read_docs(files: list[UploadFile], doc_types: list[str]) -> list[dict]:
    docs: list[dict] = []
    for f, dt in zip(files, doc_types):
        b = await f.read()
        if not b:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "INVALID_INPUT", "message": "비어있는 파일은 업로드할 수 없습니다."}},
            )
        docs.append({"filename": f.filename, "bytes": b, "doc_type": dt})
    return docs


async def _run_easy_contract_and_callback(container, case_id: int, docs: list[dict]):
    try:
        md = await container.easy_contract_service.generate(case_id=case_id, docs=docs)
        if not md.strip():
            await container.callback.post_easy_contract_error(case_id, "failed", "쉬운 계약서 생성 중 오류가 발생하였습니다.")
            return
        await container.callback.post_easy_contract_markdown(case_id, md)

    except RuntimeError as e:
        if str(e) == "UNPROCESSABLE_DOCUMENT":
            await container.callback.post_easy_contract_error(
                case_id,
                "UNPROCESSABLE_DOCUMENT",
                "문서를 처리할 수 없습니다. 파일이 손상되었거나 암호화되어 있을 수 있습니다.",
            )
        else:
            await container.callback.post_easy_contract_error(case_id, "failed", "쉬운 계약서 생성 중 오류가 발생하였습니다.")

    except Exception:
        await container.callback.post_easy_contract_error(case_id, "failed", "쉬운 계약서 생성 중 오류가 발생하였습니다.")

# ==================================
# 2) 테스트용: 동기(즉시 반환) API
#    - 콜백 X
#    - 바로 markdown 반환
# ==================================
@router.post(
    "/sync",
    response_class=PlainTextResponse,
    responses={
        200: {"content": {"text/markdown": {}}},
        400: {"description": "입력값 오류"},
    },
)
async def create_easy_contract_sync(
    files: list[UploadFile] = File(..., description="pdf/png/jpg 최대 5개"),
    doc_types: list[str] = Form(..., description="files와 같은 순서의 타입"),
    container=Depends(get_container),
):
    _validate_inputs(files, doc_types)
    docs = await _read_docs(files, doc_types)

    try:
        md = await container.easy_contract_service.generate(case_id=-1, docs=docs)
        if not md.strip():
            raise HTTPException(
                status_code=500,
                detail={"error": {"code": "failed", "message": "쉬운 계약서 생성 중 오류가 발생하였습니다."}},
            )
        # markdown을 그대로 반환
        return PlainTextResponse(content=md, media_type="text/markdown; charset=utf-8")

    except RuntimeError as e:
        if str(e) == "UNPROCESSABLE_DOCUMENT":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "UNPROCESSABLE_DOCUMENT",
                        "message": "문서를 처리할 수 없습니다. 파일이 손상되었거나 암호화되어 있을 수 있습니다.",
                    }
                },
            )
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "failed", "message": "쉬운 계약서 생성 중 오류가 발생하였습니다."}},
        )

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "failed", "message": "쉬운 계약서 생성 중 오류가 발생하였습니다."}},
        )



# =========================
# 1) 운영용: 비동기(콜백) API
# =========================
@router.post("/{id}", response_model=EasyContractAcceptedResponse, status_code=202)
async def create_easy_contract(
    background_tasks: BackgroundTasks,
    id: int = Path(..., description="쉬운계약서 식별자(int)"),
    files: list[UploadFile] = File(..., description="pdf/png/jpg 최대 5개"),
    doc_types: list[str] = Form(..., description="files와 같은 순서의 타입 (contract/registry/building_register 등)"),
    container=Depends(get_container),
):
    _validate_inputs(files, doc_types)
    docs = await _read_docs(files, doc_types)

    background_tasks.add_task(_run_easy_contract_and_callback, container, id, docs)
    return EasyContractAcceptedResponse(id=id, message="요청이 접수되었습니다.")


