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

# Initialize image generation semaphore - limit concurrent requests
semaphore = asyncio.Semaphore(2)  # Allow 2 concurrent image generations

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
                width=768,
            )
        )

        if not image_response or not image_response.data:
            raise ValueError("Invalid response from Together AI")

        image_url = image_response.data[0].url
        return image_url

    except Exception as e:
        logging.error(f"❌ Image generation failed: {e}")
        return ""  # Return empty string on failure

async def generate_image_flux_free_async(prompt: str) -> str:
    """Asynchronously generate an image using the Together AI API with free tier."""
    try:
        async with semaphore:  # Limit concurrent requests
            response = await async_client.images.generate(
                model="black-forest-labs/FLUX.1-schnell",
                prompt=prompt,
                steps=12,
                n=1,
                height=768,
                width=768,
            )

            if not response or not response.data:
                raise ValueError("Invalid response from Together AI")

            return response.data[0].url
    
    except Exception as e:
        logging.error(f"❌ Image generation failed: {e}")
        return ""  # Return empty string on failure

def get_gemini_client():
    """Create and return a new Gemini client."""
    return genai.Client(
        vertexai=True,
        project="thematic-land-451915-j3",
        location="us-central1",
    )

def generate_image_gemini(prompt):
    """Generates an image synchronously using the Gemini API."""
    try:
        # Add a small delay to avoid rate limiting
        time.sleep(1)
        
        # Get a fresh client
        client_gemini = get_gemini_client()
        
        response = client_gemini.models.generate_images(
            model='imagen-3.0-generate-002',
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",
            )
        )
        
        if response and response.generated_images:
            return response.generated_images[0].image.image_bytes
        else:
            logging.error("API did not return any generated images.")
            return None
    except Exception as e:
        logging.error(f"Error generating image with Gemini: {e}", exc_info=True)
        return None

async def upload_image_gg_storage_async(image_bytes, bucket_name, prefix):
    """Uploads an image asynchronously to Google Cloud Storage."""
    if image_bytes is None:
        logging.error("Cannot upload None image bytes")
        return ""
        
    try:
        blob_name = f"{prefix}{uuid.uuid4()}.png"
        
        # Use run_in_executor to make the synchronous GCS operations non-blocking
        loop = asyncio.get_running_loop()
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        if not await loop.run_in_executor(None, bucket.exists):
            logging.error(f"Bucket {bucket_name} does not exist.")
            return ""
            
        blob = bucket.blob(blob_name)
        await loop.run_in_executor(
            None, 
            lambda: blob.upload_from_string(image_bytes, content_type="image/png")
        )
        
        return blob.public_url
    except Exception as e:
        logging.error(f"Error uploading image: {e}", exc_info=True)
        return ""

async def generate_image_gemini_async(prompt):
    """Generate an image using the Gemini AI API asynchronously and return raw image bytes."""
    async with semaphore:  # Limit to 2 concurrent requests
        try:
            # Run the synchronous Gemini image generation in a thread pool
            loop = asyncio.get_running_loop()
            image_bytes = await loop.run_in_executor(
                executor,
                lambda: generate_image_gemini(prompt)
            )
            return image_bytes
            
        except Exception as e:
            logging.error(f"Error in generate_image_gemini_async: {e}", exc_info=True)
            return None

async def generate_and_upload_async(prompt, prefix="gemini_image_", bucket_name="bucket_comic"):
    """Generates an image and uploads it asynchronously, returning the public URL."""
    try:
        image_bytes = await generate_image_gemini_async(prompt)
        if image_bytes is None:
            logging.error(f"Failed to generate image for prompt: {prompt}")
            return ""

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{prefix}{timestamp}_{unique_id}.png"

        url = await upload_image_gg_storage_async(image_bytes, bucket_name, prefix)
        return url or ""
    except Exception as e:
        logging.error(f"Error in generate_and_upload_async: {e}", exc_info=True)
        return ""