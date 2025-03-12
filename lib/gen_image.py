from together import Together
import uuid
import datetime
import os
import logging
import asyncio
from together import AsyncTogether

from google import genai
from google.genai import types
from google.cloud import storage 
from io import BytesIO
import concurrent.futures
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Use a ThreadPoolExecutor with limited workers to prevent API overload
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# Initialize Together clients
client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
async_client = AsyncTogether(api_key=os.environ.get("TOGETHER_API_KEY"))
def get_gemini_client():
    """Create and return a new Gemini client."""
    return genai.Client(
        vertexai=True,
        project="thematic-land-451915-j3",
        location="us-central1",
    )

client_gemini = get_gemini_client()
# Initialize image generation semaphore - limit concurrent requests
semaphore = asyncio.Semaphore(1)  # Allow 1 concurrent image generation
rate_limit_delay = 60/20
# Define a placeholder image URL for error cases
PLACEHOLDER_ERROR_IMAGE = "/placeholder-error.png"  # Local path to avoid Next.js domain issues

async def generate_image_flux_async(prompt: str) -> str:
    """Asynchronously generate an image using the Together AI API."""
    loop = asyncio.get_running_loop()
    try:
        image_response = await loop.run_in_executor(
            executor,
            lambda: client.images.generate(
                prompt=prompt,
                model="black-forest-labs/FLUX.1-schnell",
                steps=14,
                n=1,
                height=1024,
                width=1024,
            )
        )

        if not image_response or not image_response.data:
            logging.warning("Empty response from Together AI")
            return PLACEHOLDER_ERROR_IMAGE

        image_url = image_response.data[0].url
        return image_url

    except Exception as e:
        logging.error(f"❌ Image generation failed: {e}")
        return PLACEHOLDER_ERROR_IMAGE  # Return placeholder on failure

async def generate_image_flux_free_async(prompt: str) -> str:
    """Asynchronously generate an image using the Together AI API with free tier."""
    try:
        # Implement exponential backoff for rate limiting
        max_retries = 3
        retry_delay = 2  # Start with 2 seconds
        
        for attempt in range(max_retries):
            try:
                response = await async_client.images.generate(
                    model="black-forest-labs/FLUX.1-schnell-free",
                    # model="black-forest-labs/FLUX.1-schnell",
                    prompt=prompt,
                    steps=4,
                    n=1,
                    height=512,
                    width=512,
                )
                
                if not response or not response.data:
                    logging.warning("Empty response from Together AI free tier")
                    return PLACEHOLDER_ERROR_IMAGE
                
                return response.data[0].url
                
            except Exception as e:
                if "rate limit" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logging.info(f"Rate limited, retrying in {wait_time} seconds (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise  # Re-raise if not a rate limit or we're out of retries
    
    except Exception as e:
        logging.error(f"❌ Image generation failed after retries: {e}")
        return PLACEHOLDER_ERROR_IMAGE  # Return placeholder on failure

# 3
def generate_image_gemini(prompt):
    """Generates an image using the Gemini API with simple retry logic."""
    max_retries = 3
    retry_delay = 2  # Start with 2 seconds
    
    for attempt in range(max_retries):
        try:
            print(f"Generating image with Gemini... (attempt {attempt+1}/{max_retries})")
            
            response = client_gemini.models.generate_images(
                model='imagen-3.0-fast-generate-001',
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                )
            )
            
            if response and response.generated_images:
                return response.generated_images[0].image.image_bytes
            else:
                logging.warning("Empty response from Gemini API")
                
        except Exception as e:
            logging.warning(f"Attempt {attempt+1} failed: {e}")
        
        # If we get here, we need to retry after a delay
        if attempt < max_retries - 1:
            wait_time = retry_delay * (2 ** attempt)
            print(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
    
    # If we've exhausted all retries
    logging.error("Failed to generate image after all retry attempts")
    return None

async def upload_image_gg_storage_async(image_bytes, bucket_name, prefix):
    """Uploads an image asynchronously to Google Cloud Storage."""
    if image_bytes is None:
        logging.error("Cannot upload None image bytes")
        return PLACEHOLDER_ERROR_IMAGE
        
    try:
        blob_name = f"{prefix}{uuid.uuid4()}.png"
        
        # Use run_in_executor to make the synchronous GCS operations non-blocking
        loop = asyncio.get_running_loop()
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        if not await loop.run_in_executor(None, bucket.exists):
            logging.error(f"Bucket {bucket_name} does not exist.")
            return PLACEHOLDER_ERROR_IMAGE
            
        blob = bucket.blob(blob_name)
        await loop.run_in_executor(
            None, 
            lambda: blob.upload_from_string(image_bytes, content_type="image/png")
        )
        
        return blob.public_url
    except Exception as e:
        logging.error(f"Error uploading image: {e}", exc_info=True)
        return PLACEHOLDER_ERROR_IMAGE

# 2
# async def generate_image_gemini_async(prompt):
#     """Generate an image using the Gemini AI API asynchronously and return raw image bytes."""
#     async with semaphore:  # Limit concurrent requests
#         try:
#             # Run the synchronous Gemini image generation in a thread pool
#             loop = asyncio.get_running_loop()
#             image_bytes = await loop.run_in_executor(
#                 executor,
#                 lambda: generate_image_gemini(prompt)
#             )
#             return image_bytes
            
#         except Exception as e:
#             logging.error(f"Error in generate_image_gemini_async: {e}", exc_info=True)
#             return None

async def generate_image_gemini_async(prompt):
    """Generate an image using Gemini API asynchronously while respecting rate limits."""
    async with semaphore:  # Ensure one-at-a-time execution
        await asyncio.sleep(rate_limit_delay)  # Enforce delay between requests
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: generate_image_gemini(prompt))
    
# 1
async def generate_and_upload_async(prompt, prefix="gemini_image_", bucket_name="bucket_comic"):
    """Generates an image and uploads it asynchronously, returning the public URL or placeholder."""
    try:
        image_bytes = await generate_image_gemini_async(prompt)
        if image_bytes is None:
            logging.error(f"⚠️ Failed to generate image for prompt: {prompt}")
            return PLACEHOLDER_ERROR_IMAGE

        url = await upload_image_gg_storage_async(image_bytes, bucket_name, prefix)
        print(f"✅ Uploaded Image URL: {url}")

        # Ensure we don't return example.com URLs or other unconfigured domains
        if "example.com" in url or not url:
            return PLACEHOLDER_ERROR_IMAGE
            
        return url
    except Exception as e:
        logging.error(f"❌ Error in generate_and_upload_async: {e}")
        return PLACEHOLDER_ERROR_IMAGE