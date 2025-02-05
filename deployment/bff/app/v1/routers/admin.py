from docarray import Document
from fastapi import APIRouter, HTTPException

from deployment.bff.app.v1.models.admin import (
    UpdateApiKeysRequestModel,
    UpdateEmailsRequestModel,
)
from deployment.bff.app.v1.models.helper import BaseRequestModel
from deployment.bff.app.v1.routers.helper import jina_client_post

router = APIRouter()


@router.post(
    "/updateUserEmails",
    summary='update user emails during runtime',
)
def update_user_email(data: UpdateEmailsRequestModel):
    """
    Update the list of emails for the security executor
    """
    jina_client_post(
        request_model=data,
        inputs=[Document()],
        endpoint='/admin/updateUserEmails',
        parameters={'user_emails': data.user_emails},
    )


@router.post(
    "/updateApiKeys",
    summary='update api keys during runtime',
)
def update_api_keys(data: UpdateApiKeysRequestModel):
    """
    Update the list of api keys for the security executor
    """
    jina_client_post(
        request_model=data,
        inputs=[Document()],
        endpoint='/admin/updateApiKeys',
        parameters={'api_keys': data.api_keys},
    )


@router.post(
    "/getStatus",
    summary='Get status of the flow during runtime',
)
def get_host_status(data: BaseRequestModel):
    """
    Get the status of the host in the request body
    """
    try:
        jina_client_post(
            request_model=data,
            inputs=[Document()],
            endpoint='/dry_run',
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return 'SUCCESS'
