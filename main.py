import os
import uuid
import json
from typing import List
import time
import asyncio
from io import BytesIO
import base64

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select, Session
from dotenv import load_dotenv

from database import get_session, init_db
from models import Comic, ComicRequest, ComicResponse
from lib.gen_image import generate_image_flux_async, generate_image_flux_free_async #, generate_and_upload_async
from lib.gen_text import groq_text_generation, deepseek_text_generation, openai_text_generation


# ✅ Load environment variables
load_dotenv()

# ✅ Initialize FastAPI App
app = FastAPI()

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
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
    finally:
        session.close()


@app.on_event("startup")
def on_startup():
    init_db()




@app.post("/generate-comic", response_model=ComicResponse)
async def generate_comic(request: ComicRequest, db: Session = Depends(get_db)):
    """Generates a comic using OpenAI and stores it in the database."""

    print(f"=========== Start doing backend")
    start_time = time.time()  # Start timing
    comic_id = str(uuid.uuid4())

    comic_list = openai_text_generation(request)
    # comic_list = groq_text_generation(request)
    # comic_list = deepseek_text_generation(request)

    t1 = time.time()
    print(f"=========[TIME] Model generate text response time: {t1 - start_time:.2f} sec")

    together_tasks = [generate_image_flux_free_async(page["image_prompt"]) for page in comic_list['pages']]
    # ✅ Handle errors properly
    try:
        image_urls = await asyncio.gather(*together_tasks)
    except Exception as e:
        print(f"❌ Error gathering images: {e}")
        image_urls = [""] * len(comic_list)  # Return empty URLs if failure

    for page, image_url in zip(comic_list['pages'], image_urls):
        page["image_url"] = image_url

    # gemini
    # bucket_name = "bucket_comic" #replace with your bucket name.
    # prefix = "gemini_image_" # desired prefix.
    # image_urls = await asyncio.gather(*(generate_and_upload_async(page["scene"], prefix, bucket_name) for page in comic_list))

    # for scene, url in zip(comic_list, image_urls):
    #     scene["image_url"] = url

    t2 = time.time()
    print(f"=========[TIME] Model generate image time: {t2 - t1:.2f} sec")
    # Save comic in PostgreSQL
    new_comic = Comic(id=comic_id, prompt=request.prompt, 
                      pages=comic_list['pages'], summary=comic_list["summary"], title=comic_list["title"])
    # print("=============== new comic:",new_comic) 


    db.add(new_comic)
    db.commit()
    db.refresh(new_comic)

    total_time = time.time() - start_time
    print(f"========[TIME] Total execution time: {total_time:.2f} sec")

    return ComicResponse(
        id=new_comic.id,
        prompt=new_comic.prompt,
        title=new_comic.title,
        summary=new_comic.summary,
        pages=json.loads(new_comic.pages),  # Convert JSON string back to Python object
        created_at=new_comic.created_at.isoformat()
    )

    
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
        
        pages=json.loads(comic.pages),  # Convert JSON string back to Python object
        summary=comic.summary,
        title=comic.title,
        created_at=comic.created_at.isoformat()
    )
