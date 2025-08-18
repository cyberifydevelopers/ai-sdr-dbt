from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, File as FastAPIFile, Depends
from helpers.token_helper import get_current_user
from helpers.get_user_admin import get_user_admin
# from models.logs import Logs
from models.auth import User
from models.documents import Documents
from typing import Annotated
import httpx
import os
import io
from helpers.vapi_helper import get_headers, generate_token, get_file_headers
import requests

vapi_header = get_headers()
router = APIRouter()

token = generate_token()

@router.post("/documents")
async def upload_documents(user: Annotated[User, Depends(get_current_user)],
 file: UploadFile = FastAPIFile(...), name : str = Form(...)):
    try:
        if file.filename.split(".")[-1].lower() not in ["pdf", "doc", "docx", "txt"]:
            raise HTTPException(
                status_code=400,
                detail="Unsupported Format. Only PDF and DOC/DOCX files are allowed."
            )
        # headers = {
        #     "Authorization": f"Bearer {token}"
        # }
        vapi_url = "https://api.vapi.ai/file"
        async with httpx.AsyncClient() as client:
            print("Content type of file is: ", file.content_type)
            vapi_response = await client.post(
                vapi_url,
                headers=get_file_headers(),
                files={"file": (f"{name}.{file.filename.split(".")[-1].lower()}",  io.BytesIO(await file.read()), file.content_type)}
            )
        if vapi_response.status_code not in [200, 201]:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file to vapi.ai: {vapi_response.text}"
            )

        print(vapi_response.headers)
        
        vapi_file_id = vapi_response.json().get("id")

        file_record = Documents(file_name=name, user=user, vapi_file_id=vapi_file_id)
        await file_record.save()
        # await Logs.create(
        #         user = user,
        #         message = f"uploaded a document {name}",
        #         short_message = "upload_document"
        #  )
        return {"success": True, "detail": "File uploaded successfully!", "file_id": vapi_file_id, "file_name": name}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Document Upload Failed!!\n{str(e)}")


@router.get("/vapi_docs")
async def vapi_docs(user: Annotated[User, Depends(get_current_user)]):
    try:
        return await Documents.filter(user_id=user.id).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch files\n{str(e)}")


@router.get("/all_vapi_docs")
async def vapi_docs(user: Annotated[User, Depends(get_current_user)]):
    try:
        return [
            {
                **dict(document),
                "user_name": document.user.name if document.user else None
            }
            for document in await Documents.all().prefetch_related("user")
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch files\n{str(e)}")
    
    
    
@router.delete("/delete_vapi_doc/{vapi_file_id}")
async def delete_vapi_doc(
    vapi_file_id: str,
    user: Annotated[User, Depends(get_current_user)],    
    # main_admin: Annotated[User, Depends(get_user_admin)],

):
    try:
        print("vapi_header:",vapi_header)
        document = await Documents.get(vapi_file_id=vapi_file_id , user_id= user.id) 
        vapi_url = f"https://api.vapi.ai/file/{vapi_file_id}"
       
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(vapi_url, headers=get_file_headers())
        print("Response:",response)
        if response.status_code in [200, 204]:
            await document.delete()
            # await Logs.create(
            #     user = user,
            #     message = f"deleted a document {document.file_name}",
            #     short_message = "delete_document"
            # )
            return {"success": True, "detail": "Document deleted successfully."}
        else:
            response_data = response.json()
            raise HTTPException(status_code=response.status_code, detail=f"Failed to delete from vapi: {response_data.get('message')}")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

