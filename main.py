import os
import logging
import uuid
import time
import asyncio
import requests
from sqlalchemy import desc, text
from typing import List, Dict, Any, Optional

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks, Request, WebSocket, WebSocketDisconnect, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select, Session
from dotenv import load_dotenv

from database import get_session, init_db, commit_with_retry
from models import Comic, ComicRequest, ComicResponse
from lib.gen_image import (generate_image_flux_async, generate_image_flux_free_async,
                          generate_and_upload_async, generate_image_gemini,
                          upload_image_gg_storage_async)
from lib.gen_text import groq_text_generation, deepseek_text_generation, openai_text_generation, gemini_text_generation, generate_new_comic_pages
from lib.init_gemini import init_vertexai

# Load environment variables
load_dotenv()

# Initialize FastAPI App
app = FastAPI()

# Store active generation tasks
active_tasks = set()

# Store WebSocket connections
connected_clients: List[WebSocket] = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #"https://comic.thietkeai.com", "http://localhost:3000"
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

# WebSocket endpoint for real-time updates
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    
    
    try:
        await websocket.accept()
        print(f"Incoming WebSocket connection request from {websocket.client}")
        await websocket.send_json({"message": "Hello from FastAPI WebSocket!"})
        connected_clients.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(connected_clients)}")
        
        # Keep connection alive
        while True:
            try:
                # Wait for messages (will keep connection open)
                data = await websocket.receive_text()
                logger.debug(f"Received message from WebSocket client: {data}")
            except WebSocketDisconnect:
                logger.info("WebSocket client disconnected normally")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket connection: {e}")
                break
                
    except Exception as e:
        logger.error(f"Error accepting WebSocket connection: {str(e)}")
    finally:
        # Remove client on disconnection
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info(f"WebSocket client removed. Remaining clients: {len(connected_clients)}")

# Broadcast a message to all connected WebSocket clients
async def broadcast_comic_update(comic_id: str, db: Session):
    """Broadcast comic updates to all connected WebSocket clients."""
    if not connected_clients:
        return
    
    # Fetch the latest comic data
    comic = db.get(Comic, comic_id)
    if not comic:
        logger.error(f"Cannot broadcast update for comic {comic_id} - not found")
        return
    
    # Prepare the message
    message = {
        "type": "comic_update",
        "comic": {
            "id": comic.id,
            "prompt": comic.prompt,
            "title": comic.title,
            "summary": comic.summary,
            "pages": comic.pages,
            "created_at": comic.created_at.isoformat() if comic.created_at else None,
            "status": comic.status
        }
    }
    
    # Send to all connected clients
    for client in connected_clients.copy():  # Use a copy to avoid modification during iteration
        try:
            await client.send_json(message)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            # Failed clients will be removed when they disconnect

async def generate_comic_text(request: ComicRequest):
    """Generate comic text, isolated to make it easier to run in thread pool."""
    return gemini_text_generation(request)

PLACEHOLDER_ERROR_IMAGE = "/images/placeholder-error.png"  # Local path to avoid Next.js domain issues

# async def generate_comic_images(comic_list):
#     """Generate and upload images for comic pages (Gemini) ensuring all uploads complete before broadcasting."""
#     bucket_name = "bucket_comic"
#     prefix = "gemini_image_"

#     image_tasks = []
#     for page in comic_list['pages']:
#         task = asyncio.create_task(
#             generate_and_upload_async(page["image_prompt"], prefix, bucket_name)
#         )
#         image_tasks.append((page, task))

#     # Wait for all image uploads to complete
#     for page, task in image_tasks:
#         try:
#             url = await asyncio.wait_for(task, timeout=120)
#             page["image_url"] = url if url else PLACEHOLDER_ERROR_IMAGE
#         except asyncio.TimeoutError:
#             logging.error(f"Timeout generating image for: {page['image_prompt'][:30]}...")
#             page["image_url"] = PLACEHOLDER_ERROR_IMAGE
#         except Exception as e:
#             logging.error(f"Error generating image: {e}")
#             page["image_url"] = PLACEHOLDER_ERROR_IMAGE

#     return comic_list  # ✅ Return the full comic object, not just pages

async def generate_comic_images(comic_list):
    """Generate and upload images for comic pages (Gemini) and return only the image URLs."""
    bucket_name = "bucket_comic"
    prefix = "gemini_image_"

    # Create async tasks for all image generation & uploads
    image_tasks = [
        generate_and_upload_async(page["image_prompt"], prefix, bucket_name)
        for page in comic_list['pages']
    ]

    # Run all tasks concurrently (but respecting Gemini API rate limits)
    image_urls = await asyncio.gather(*image_tasks, return_exceptions=True)

    # Handle errors and return only image URLs
    processed_urls = [
        url if isinstance(url, str) and url else PLACEHOLDER_ERROR_IMAGE
        for url in image_urls
    ]

    return processed_urls  # ✅ Return only the list of image URLs

async def generate_comic_images_flux(comic_list):
    """Generate and upload images asynchronously using Together AI."""
    logging.info(f"🚀 Starting image generation for {len(comic_list['pages'])} pages.")

    # Process pages in batches to avoid rate limits
    batch_size = 5  # Adjust based on rate limits
    all_pages = comic_list["pages"]
    
    for i in range(0, len(all_pages), batch_size):
        batch_pages = all_pages[i:i+batch_size]
        logging.info(f"Processing batch {i//batch_size + 1} with {len(batch_pages)} pages")
        
        # Generate images for this batch
        image_tasks = []
        for page in batch_pages:
            task = asyncio.create_task(generate_image_flux_free_async(page["image_prompt"]))
            image_tasks.append((page, task))
        
        # Wait for batch to complete with timeout
        for page, task in image_tasks:
            try:
                # Add timeout to prevent hanging
                url = await asyncio.wait_for(task, timeout=60)
                
                # Validate URL before assigning
                if not url or "example.com" in url:
                    page["image_url"] = PLACEHOLDER_ERROR_IMAGE
                else:
                    page["image_url"] = url
                    
                logging.info(f"✅ Image URL set: {page['image_url'][:60]}...")
            except asyncio.TimeoutError:
                logging.error(f"⏱️ Timeout generating image for prompt: {page['image_prompt'][:30]}...")
                page["image_url"] = PLACEHOLDER_ERROR_IMAGE
            except Exception as e:
                logging.error(f"❌ Error generating image: {e}")
                page["image_url"] = PLACEHOLDER_ERROR_IMAGE
        
        # Add a delay between batches to avoid rate limits
        if i + batch_size < len(all_pages):
            await asyncio.sleep(6)  # Wait 6 seconds between batches
    
    return comic_list

async def process_comic_generation(request: ComicRequest, db: Session, comic_id: str):
    """Process comic generation in stages, updating the database as we go."""
    logger.info(f"Starting comic generation for ID: {comic_id}")
    start_time = time.time()
    
    try:
        # Step 1: Generate text
        loop = asyncio.get_running_loop()
        comic_list = await loop.run_in_executor(None, lambda: gemini_text_generation(request))
        
        # # Update the comic with text content but no images yet
        # visibility = "private" if request.user_id else "community"
        
        comic = db.get(Comic, comic_id)
        # ✅ Step 1.1: Store text in the database
        comic = db.get(Comic, comic_id)
        if not comic:
            logger.error(f"Comic {comic_id} not found in database")
            return

        comic.title = comic_list["title"]
        comic.summary = comic_list["summary"]
        comic.pages = comic_list["pages"]  # ✅ Ensure text is stored before moving to images
        comic.status = "processing"
        db.add(comic)
        commit_with_retry(db)  # ✅ Ensure Step 1 commits fully

        logger.info(f"✅ Text generation completed for {comic_id}, proceeding to image generation")

        # ✅ Broadcast update with text content before generating images
        await broadcast_comic_update(comic_id, db)

        # ✅ Step 2: Generate images **only if pages exist**
        if not comic.pages or len(comic.pages) == 0:
            logger.error(f"❌ No pages found for {comic_id}, skipping image generation")
            return
        
        
        text_time = time.time()
        logger.info(f"Text generation completed in {text_time - start_time:.2f} seconds")
        
        # Step 2: Generate images (this runs concurrently for all images)
        # comic_list = await generate_comic_images_flux(comic_list)
        # comic_list = await generate_comic_images(comic_list)
        image_urls = await generate_comic_images(comic_list)
        
        # ✅ Efficiently update JSONB image URLs one by one
        for idx, image_url in enumerate(image_urls):
            sql = """
            UPDATE comic 
            SET pages = jsonb_set(pages, '{%s, image_url}', '"%s"')
            WHERE id = :comic_id
            """ % (idx, image_url)
            db.execute(text(sql), {"comic_id": comic_id})

            # ✅ Commit every 3 updates to avoid large transactions
            if idx % 3 == 0 or idx == len(image_urls) - 1:
                commit_with_retry(db)
                await broadcast_comic_update(comic_id, db)

        # ✅ Final update: Set comic status to "completed"
        db.execute(text("UPDATE comic SET status = 'completed' WHERE id = :comic_id"),
                   {"comic_id": comic_id})
        commit_with_retry(db)

        await broadcast_comic_update(comic_id, db)
        send_webhook(comic_id)

        total_time = time.time() - start_time
        logger.info(f"Total comic generation time: {total_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Error in comic generation: {e}", exc_info=True)
        try:
            db.execute(text("UPDATE comic SET status = 'failed' WHERE id = :comic_id"),
                       {"comic_id": comic_id})
            commit_with_retry(db)
            await broadcast_comic_update(comic_id, db)
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
    
    # Broadcast new comic to all connected clients
    await broadcast_comic_update(comic_id, db)
    
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
from pydantic import BaseModel

class ExtendComicRequest(BaseModel):
    prompt: Optional[str]  # ✅ Defines 'prompt' as a required field
# Update the extend_comic function to use WebSockets too
@app.put("/comic/{comic_id}/extend", response_model=ComicResponse)
async def extend_comic(comic_id: str, 
                       request_body: ExtendComicRequest,
                    #    request: Request, 
                    #    background_tasks: BackgroundTasks, 
                       db: Session = Depends(get_db)):
    """Extends a comic by generating new pages and images asynchronously."""
    
    # data = await request.json()
    # prompt = data.get("prompt")

    prompt = request_body.prompt

    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt in request")

    comic = db.get(Comic, comic_id)
    
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    # Step 1: generating text for new pages
    original_pages = comic.pages
    new_pages = generate_new_comic_pages(original_pages, num_pages=3)
    
    # Initialize new pages with empty image URLs
    new_pages = [{**new_page, 'image_url': ""} for new_page in new_pages]
    
    # Step 2: Store new pages in database first
    combined_pages = original_pages + new_pages    
    comic.pages = combined_pages
    comic.status = "processing"
    db.add(comic)
    commit_with_retry(db)
    
    # Broadcast the update
    await broadcast_comic_update(comic_id, db)
    
    # ✅ Step 3: Generate images separately in background
    task = asyncio.create_task(process_extended_pages(comic_id, len(original_pages), new_pages, db))
    
    # Keep track of task to prevent garbage collection
    active_tasks.add(task)
    task.add_done_callback(lambda t: active_tasks.remove(t))
    
    logger.info(f"Started background task to extend comic {comic_id} with {len(new_pages)} new pages")
    
    # Return the comic with the new pages (images will be generated in background)
    return ComicResponse(
        id=comic.id,
        prompt=comic.prompt,
        title=comic.title,
        summary=comic.summary,
        pages=comic.pages,  # No images yet, will be added asynchronously
        created_at=comic.created_at.isoformat() if comic.created_at else None,
        status="processing"
    )

async def process_extended_pages(comic_id: str,  start_idx: int, new_pages: list, db: Session):
    """Process image generation for extended comic pages, ensuring GCS uploads are completed before broadcasting."""
    start_time = time.time()
    logger.info(f"Starting image generation for extended comic {comic_id} with {len(new_pages)} new pages")

    try:
        comic = db.get(Comic, comic_id)
        if not comic:
            logger.error(f"Comic {comic_id} not found during extension processing")
            return

        # ✅ Step 1: Generate images for new pages. Generate images for new pages and return full comic object
        image_urls = await generate_comic_images({"pages": new_pages})
        
        # ✅ Step 2: Update only `image_url` fields in JSONB
        # not using this because of not efficient
        # updated_new_pages = updated_comic["pages"]  # ✅ Extract updated new pages

        # ✅ Step 2: Update only `image_url` fields in JSONB
        for idx, image_url in enumerate(image_urls):
            sql = """
            UPDATE comic 
            SET pages = jsonb_set(pages, '{%s, image_url}', '"%s"')
            WHERE id = :comic_id
            """ % (start_idx + idx, image_url)
            db.execute(text(sql), {"comic_id": comic_id})

            # ✅ Commit updates every 3 pages
            if idx % 3 == 0 or idx == len(image_urls) - 1:
                commit_with_retry(db)
                await broadcast_comic_update(comic_id, db)

        # ✅ Step 3: Final update to set status to "completed"
        db.execute(text("UPDATE comic SET status = 'completed' WHERE id = :comic_id"),
                   {"comic_id": comic_id})
        commit_with_retry(db)

        await broadcast_comic_update(comic_id, db)
        send_webhook(comic_id)

        total_time = time.time() - start_time
        logger.info(f"Extended comic image generation completed in {total_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Error in comic extension process: {e}", exc_info=True)
        try:
            db.execute(text("UPDATE comic SET status = 'failed' WHERE id = :comic_id"),
                       {"comic_id": comic_id})
            commit_with_retry(db)
            await broadcast_comic_update(comic_id, db)
        except Exception as db_error:
            logger.error(f"Failed to update comic status after extension error: {db_error}")

# Existing route implementations...
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
    
@app.get("/comics", response_model=List[ComicResponse])
async def get_user_comics(
    request: Request,  # ✅ Use Request to manually extract headers
    db: Session = Depends(get_db),
):
    """Fetch comics only for the authenticated user."""
    try:
        user_id = request.headers.get("X-User-Id")  # ✅ Extract from headers manually

        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized: Missing user ID")

        # Query only comics that belong to the user
        comics = (
            db.query(Comic)
            .filter(Comic.user_id == user_id)
            .order_by(desc(Comic.created_at))
            .limit(100)
            .all()
        )

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
        return []

@app.get("/comics-public", response_model=list[ComicResponse])
async def get_all_comics_public(db: Session = Depends(get_db)):
    """Fetch all comics from the database."""
    try:
        # Use a more efficient query
        query = db.query(Comic).filter(Comic.visibility == "community").order_by(desc(Comic.created_at)).limit(30)
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

@app.put("/comic/{comic_id}/reload-page/{page_index}", response_model=ComicResponse)
async def reload_comic_page(comic_id: str, page_index: int, db: Session = Depends(get_db)):
    """Re-generates the image for a specific page in the comic."""
    logger.info(f"Reloading image for comic {comic_id}, page {page_index}")

    comic = db.get(Comic, comic_id)
    
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    # Validate page index
    if page_index < 0 or page_index >= len(comic.pages):
        raise HTTPException(status_code=400, detail="Invalid page index")

    page = comic.pages[page_index]

    # ✅ Ensure the page has an image prompt to regenerate
    if "image_prompt" not in page or not page["image_prompt"]:
        raise HTTPException(status_code=400, detail="Page does not have an image prompt")

    # ✅ Regenerate only the failed/missing image
    image_url = await generate_and_upload_async(page["image_prompt"])

    # ✅ Update only the `image_url` field in the JSONB column
    sql = """
    UPDATE comic 
    SET pages = jsonb_set(pages, '{%s, image_url}', '"%s"')
    WHERE id = :comic_id
    """ % (page_index, image_url)

    db.execute(text(sql), {"comic_id": comic_id})
    commit_with_retry(db)

    # ✅ Broadcast the update
    await broadcast_comic_update(comic_id, db)

    logger.info(f"Reloaded image for comic {comic_id}, page {page_index}")
    
    return ComicResponse(
        id=comic.id,
        prompt=comic.prompt,
        title=comic.title,
        summary=comic.summary,
        pages=comic.pages,  # ✅ Updated with new image
        created_at=comic.created_at.isoformat() if comic.created_at else None,
        status="completed"
    )


@app.get("/image-queue-size")
async def get_image_queue_size():
    """Returns the current size of the active generation tasks."""
    return {"active_tasks": len(active_tasks)}