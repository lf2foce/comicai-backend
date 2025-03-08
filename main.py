import os
import logging

import uuid
import json
import time
import asyncio
import requests
from sqlalchemy import desc  # ✅ Import `desc` for ordering

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select, Session
from dotenv import load_dotenv

from database import get_session, init_db, commit_with_retry
from models import Comic, ComicRequest, ComicResponse
from lib.gen_image import (generate_image_flux_async, generate_image_flux_free_async , 
                           generate_and_upload_async, 
                            generate_image_gemini, 
                            upload_image_gg_storage_async)
from lib.gen_text import groq_text_generation, deepseek_text_generation, openai_text_generation, gemini_text_generation
from lib.init_gemini import init_vertexai


# ✅ Load environment variables
load_dotenv()

# ✅ Initialize FastAPI App
app = FastAPI()
image_queue = asyncio.Queue()
# ✅ Ensure ALL origins that need access are included
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://comic.thietkeai.com", "http://localhost:3000"], # Only allow these origins
    allow_origin_regex="https://.*",  # Ensures subdomains work
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Dependency Injection for Database Session
def get_db():
    session = next(get_session())
    try:
        yield session
    finally:
        session.close()

@app.on_event("startup")
def on_startup():
    init_db()
    init_vertexai()




# @app.post("/generate-comic", response_model=ComicResponse)
# async def generate_comic(request: ComicRequest, db: Session = Depends(get_db)):
#     """Generates a comic using OpenAI and stores it in the database."""

#     print(f"=========== Start doing backend")
#     start_time = time.time()  # Start timing
#     comic_id = str(uuid.uuid4())

#     try:
#         # comic_list = openai_text_generation(request)
#         # comic_list = groq_text_generation(request)
#         # comic_list = deepseek_text_generation(request)
#         comic_list = gemini_text_generation(request)
#         print("✅ Successfully generated comic text")
#     except Exception as e:
#         print(f"❌ Error in text generation: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Text generation error: {str(e)}")
    
    

#     t1 = time.time()
#     print(f"=========[TIME] Model generate text response time: {t1 - start_time:.2f} sec")

#     together_tasks = [generate_image_flux_free_async(page["image_prompt"]) for page in comic_list['pages']]
#     # # ✅ Handle errors properly
#     try:
#         image_urls = await asyncio.gather(*together_tasks)
#     except Exception as e:
#         print(f"❌ Error gathering images: {e}")
#         image_urls = [""] * len(comic_list)  # Return empty URLs if failure

#     for page, image_url in zip(comic_list['pages'], image_urls):
#         page["image_url"] = image_url

#     # gemini
#     # try:
#     #     bucket_name = "bucket_comic" #replace with your bucket name.
#     #     prefix = "gemini_image_" # desired prefix.
#     #     image_urls = await asyncio.gather(*(generate_and_upload_async(page["image_prompt"], prefix, bucket_name) for page in comic_list['pages']))

#     #     for scene, url in zip(comic_list['pages'], image_urls):
#     #         scene["image_url"] = url
#     # except Exception as e:
#     #     print(f"Error during image generation process: {e}")
#     #     # Assign placeholder URLs to all pages in case of error
#     #     for scene in comic_list['pages']:
#     #         scene["image_url"] = "placeholder_image_url.jpg"

#     t2 = time.time()
#     print(f"=========[TIME] Model generate image time: {t2 - t1:.2f} sec")
#     # Save comic in PostgreSQL
#     new_comic = Comic(id=comic_id, prompt=request.prompt, 
#                       pages=comic_list['pages'], summary=comic_list["summary"], title=comic_list["title"])
#     # print("=============== new comic:",new_comic) 


#     db.add(new_comic)
#     # ✅ Use commit_with_retry to handle intermittent failures
#     commit_with_retry(db)
#     # db.commit()
#     db.refresh(new_comic)

#     total_time = time.time() - start_time
#     print(f"========[TIME] Total execution time: {total_time:.2f} sec")

#     return ComicResponse(
#         id=new_comic.id,
#         prompt=new_comic.prompt,
#         title=new_comic.title,
#         summary=new_comic.summary,
#         # pages=json.loads(new_comic.pages),  # Convert JSON string back to Python object
#         pages=new_comic.pages,
#         created_at=new_comic.created_at.isoformat()
#     )

async def process_comic_generation(request: ComicRequest, db: Session, comic_id: str):
    """Processes comic generation and sends webhook."""
    # await image_queue.put(1)
    start_time = time.time()
    try:
        comic_list = gemini_text_generation(request)
        print("✅ Successfully generated comic text")
    except Exception as e:
        print(f"❌ Error in text generation: {str(e)}")
        return

    t1 = time.time()
    print(f"=========[TIME] Model generate text response time: {t1 - start_time:.2f} sec")

    image_urls = []
    bucket_name = "bucket_comic"
    prefix = "gemini_image_"

    # still sync 
    try:
        image_urls = await asyncio.gather(*(upload_image_gg_storage_async(generate_image_gemini(page["image_prompt"]), bucket_name, prefix) for page in comic_list['pages']))
        for scene, url in zip(comic_list['pages'], image_urls):
            scene["image_url"] = url
    except Exception as e:
        print(f"Error during image generation process: {e}")
        for scene in comic_list['pages']:
            scene["image_url"] = ""

    t2 = time.time()
    print(f"=========[TIME] Model generate image time: {t2 - t1:.2f} sec")

    visibility = "private" if request.user_id else "community"

    new_comic = Comic(id=comic_id, prompt=request.prompt, user_id=request.user_id, visibility=visibility, 
                      pages=comic_list['pages'], summary=comic_list["summary"], title=comic_list["title"])

    print(new_comic.model_dump_json(indent=2))
    db.add(new_comic)
    commit_with_retry(db)
    db.refresh(new_comic)
    

    total_time = time.time() - start_time
    print(f"========[TIME] Total execution time: {total_time:.2f} sec")

    send_webhook(new_comic.id)
    # image_queue.task_done() #bỏ task ra khỏi queue khi hoàn thành.
    # try:
    #     image_queue.task_done()
    #     logging.info("task_done called") #add log.
    # except Exception as e:
    #     logging.error(f"Error calling task_done: {e}") #add log.
    #     image_queue.task_done() #call task done anyway.

@app.post("/generate-comic", response_model=ComicResponse)
async def generate_comic(request: ComicRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Generates a comic in the background and sends a webhook."""
    comic_id = str(uuid.uuid4())
    background_tasks.add_task(process_comic_generation, request, db, comic_id)
    return ComicResponse(id=comic_id, prompt=request.prompt, title="Processing...", summary="Processing...", pages=[], created_at=str(time.time()),
                         status='processing')
    
# ✅ **Route to Retrieve Comic**
@app.get("/comic/{comic_id}", response_model=ComicResponse)
def get_comic(comic_id: str, db: Session = Depends(get_db)):
    """Retrieves a comic by ID."""
    comic = db.get(Comic, comic_id)
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    return ComicResponse(
        id=comic.id,
        prompt=comic.prompt,
        
        # pages=json.loads(comic.pages),  # Convert JSON string back to Python object
        pages=comic.pages,
        summary=comic.summary,
        title=comic.title,
        created_at=comic.created_at.isoformat(),
        status=comic.status
    )

@app.get("/comics", response_model=list[ComicResponse])
async def get_all_comics(db: Session = Depends(get_db)):

    """
    Fetch all comics from the database.
    
    """
    comics = db.query(Comic).order_by(desc(Comic.created_at)).limit(5).all() #filter(Comic.visibility == "community")
    
    # return comics
    return [
            ComicResponse(
                id=comic.id,
                prompt=comic.prompt,
                title=comic.title,
                summary=comic.summary,
                pages=comic.pages,
                created_at=comic.created_at.isoformat() if comic.created_at else None,
                status=comic.status,
            )
            for comic in comics
        ]


def send_webhook(comic_id: str):
    """Sends a webhook to Next.js based on the environment."""
    environment = os.getenv("ENVIRONMENT", "dev")  # Default to dev if not set
    if environment == "prod":
        webhook_url = os.getenv("WEBHOOK_URL_PROD")
    else:
        webhook_url = os.getenv("WEBHOOK_URL_DEV")

    if not webhook_url:
        logging.error("Webhook URL not configured for the current environment.")
        return

    try:
        response = requests.post(webhook_url, json={"comic_id": comic_id})
        response.raise_for_status()
        logging.info(f"Webhook sent successfully to {webhook_url}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending webhook: {e}")


@app.get("/image-queue-size")
async def get_image_queue_size():
    """Returns the current size of the image processing queue."""
    return {"queue_size": image_queue.qsize()}

from fastapi import Request

@app.put("/comic/{comic_id}/extend", response_model=ComicResponse)
async def extend_comic(comic_id: str, request: Request, db: Session = Depends(get_db)):
    """Extends a comic by duplicating its pages."""
    
    data = await request.json()  # ✅ Extract JSON body
    prompt = data.get("prompt")  # ✅ Get the "prompt" key from JSON

    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt in request")

    comic = db.get(Comic, comic_id)
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    original_pages = comic.pages
    new_pages = original_pages + original_pages + original_pages  # Duplicate pages 3 times

    comic.pages = new_pages
    db.add(comic)
    commit_with_retry(db)
    db.refresh(comic)

    return ComicResponse(
        id=comic.id,
        prompt=comic.prompt,
        title=comic.title,
        summary=comic.summary,
        pages=comic.pages,
        created_at=comic.created_at.isoformat(),
        status=comic.status
    )