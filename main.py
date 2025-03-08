import os
import logging
import uuid
import time
import asyncio
import requests
from sqlalchemy import desc

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select, Session
from dotenv import load_dotenv

from database import get_session, init_db, commit_with_retry
from models import Comic, ComicRequest, ComicResponse
from lib.gen_image import (generate_image_flux_async, generate_image_flux_free_async,
                          generate_and_upload_async, generate_image_gemini,
                          upload_image_gg_storage_async)
from lib.gen_text import groq_text_generation, deepseek_text_generation, openai_text_generation, gemini_text_generation
from lib.init_gemini import init_vertexai

# Load environment variables
load_dotenv()

# Initialize FastAPI App
app = FastAPI()

# Store active generation tasks
active_tasks = set()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://comic.thietkeai.com", "http://localhost:3000"],
    allow_origin_regex="https://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Dependency Injection for Database Session
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
    logger.info("Application started, database initialized")

async def generate_comic_text(request: ComicRequest):
    """Generate comic text, isolated to make it easier to run in thread pool."""
    return gemini_text_generation(request)

async def generate_comic_images(comic_list):
    """Generate and upload images for comic pages."""
    bucket_name = "bucket_comic"
    prefix = "gemini_image_"
    
    # Process each image generation independently
    image_tasks = []
    for page in comic_list['pages']:
        # Create a task for each image but don't await it yet
        task = asyncio.create_task(
            generate_and_upload_async(page["image_prompt"], prefix, bucket_name)
        )
        image_tasks.append((page, task))
    
    # As each image completes, update the page with the URL
    for page, task in image_tasks:
        try:
            url = await task
            page["image_url"] = url if url else ""
            # After each image is done, we have a partially complete comic
            logger.info(f"Generated image for prompt: {page['image_prompt'][:30]}...")
        except Exception as e:
            logger.error(f"Failed to generate image: {e}")
            page["image_url"] = ""
    
    return comic_list

async def process_comic_generation(request: ComicRequest, db: Session, comic_id: str):
    """Process comic generation in stages, updating the database as we go."""
    logger.info(f"Starting comic generation for ID: {comic_id}")
    start_time = time.time()
    
    try:
        # Step 1: Generate text
        loop = asyncio.get_running_loop()
        comic_list = await loop.run_in_executor(None, lambda: gemini_text_generation(request))
        
        # Update the comic with text content but no images yet
        visibility = "private" if request.user_id else "community"
        
        comic = db.get(Comic, comic_id)
        if comic:
            comic.title = comic_list["title"]
            comic.summary = comic_list["summary"]
            comic.pages = comic_list["pages"]  # Pages with prompts but no images yet
            comic.status = "processing"
            db.add(comic)
            commit_with_retry(db)
            logger.info(f"Updated comic {comic_id} with text content")
        else:
            logger.error(f"Comic {comic_id} not found in database")
            return
        
        text_time = time.time()
        logger.info(f"Text generation completed in {text_time - start_time:.2f} seconds")
        
        # Step 2: Generate images (this runs concurrently for all images)
        comic_list = await generate_comic_images(comic_list)
        
        # Final update with all images
        comic = db.get(Comic, comic_id)
        if comic:
            comic.pages = comic_list["pages"]
            comic.status = "completed"
            db.add(comic)
            commit_with_retry(db)
            logger.info(f"Updated comic {comic_id} with images")
        
        image_time = time.time()
        logger.info(f"Image generation completed in {image_time - text_time:.2f} seconds")
        
        # Send webhook notification
        send_webhook(comic_id)
        
        total_time = time.time() - start_time
        logger.info(f"Total comic generation time: {total_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error in comic generation: {e}", exc_info=True)
        # Update comic status to failed
        try:
            comic = db.get(Comic, comic_id)
            if comic:
                comic.status = "failed"
                db.add(comic)
                commit_with_retry(db)
        except Exception as db_error:
            logger.error(f"Failed to update comic status: {db_error}")

@app.post("/generate-comic", response_model=ComicResponse)
async def generate_comic(request: ComicRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Starts comic generation and immediately returns with a comic ID."""
    comic_id = str(uuid.uuid4())
    logger.info(f"New comic generation request received: {comic_id}")
    
    # Create placeholder comic immediately
    new_comic = Comic(
        id=comic_id,
        prompt=request.prompt,
        user_id=request.user_id,
        visibility="private" if request.user_id else "community",
        pages=[],
        summary="Your comic is being created...",
        title="Generating your comic...",
        status="processing"
    )
    
    db.add(new_comic)
    commit_with_retry(db)
    logger.info(f"Created placeholder comic: {comic_id}")
    
    # Start background task
    task = asyncio.create_task(process_comic_generation(request, db, comic_id))
    
    # Keep track of task to prevent garbage collection
    active_tasks.add(task)
    task.add_done_callback(lambda t: active_tasks.remove(t))
    
    return ComicResponse(
        id=comic_id,
        prompt=request.prompt,
        title="Generating your comic...",
        summary="Your comic is being created...",
        pages=[],
        created_at=new_comic.created_at.isoformat() if new_comic.created_at else str(time.time()),
        status='processing'
    )

@app.get("/comic/{comic_id}", response_model=ComicResponse)
def get_comic(comic_id: str, db: Session = Depends(get_db)):
    """Retrieves a comic by ID."""
    comic = db.get(Comic, comic_id)
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    return ComicResponse(
        id=comic.id,
        prompt=comic.prompt,
        pages=comic.pages,
        summary=comic.summary,
        title=comic.title,
        created_at=comic.created_at.isoformat() if comic.created_at else None,
        status=comic.status
    )
@app.get("/comics", response_model=list[ComicResponse])
async def get_all_comics(db: Session = Depends(get_db)):
    """Fetch all comics from the database."""
    try:
        # Use a more efficient query
        query = db.query(Comic).order_by(desc(Comic.created_at)).limit(10) #.filter(Comic.visibility == "community")
        comics = query.all()
        
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
    except Exception as e:
        logger.error(f"Error fetching comics: {e}", exc_info=True)
        # Return empty list instead of failing
        return []

def send_webhook(comic_id: str):
    """Sends a webhook to Next.js based on the environment."""
    environment = os.getenv("ENVIRONMENT", "dev")
    if environment == "prod":
        webhook_url = os.getenv("WEBHOOK_URL_PROD")
    else:
        webhook_url = os.getenv("WEBHOOK_URL_DEV")

    if not webhook_url:
        logger.error("Webhook URL not configured for the current environment.")
        return

    try:
        response = requests.post(webhook_url, json={"comic_id": comic_id})
        response.raise_for_status()
        logger.info(f"Webhook sent successfully to {webhook_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending webhook: {e}")

@app.get("/image-queue-size")
async def get_image_queue_size():
    """Returns the current size of the active generation tasks."""
    return {"active_tasks": len(active_tasks)}

@app.put("/comic/{comic_id}/extend", response_model=ComicResponse)
async def extend_comic(comic_id: str, request: Request, db: Session = Depends(get_db)):
    """Extends a comic by duplicating its pages."""
    
    data = await request.json()
    prompt = data.get("prompt")

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
        created_at=comic.created_at.isoformat() if comic.created_at else None,
        status=comic.status
    )