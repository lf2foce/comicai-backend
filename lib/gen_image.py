from together import Together
import uuid  # Import the uuid module for generating unique IDs
import datetime
import os
import asyncio
from together import AsyncTogether

# from google import genai
# from google.genai import types
# from google.cloud import storage 
from io import BytesIO
import base64
import concurrent.futures
import time
# executor = ThreadPoolExecutor()
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)  # ✅ Prevent overloading the API

client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
async_client = AsyncTogether(api_key=os.environ.get("TOGETHER_API_KEY"))

# client_gemini = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

# client_gemini = genai.Client(
#     vertexai=True,
#     project="thematic-land-451915-j3",
#     # location="us-central1",
#     location="asia-southeast1",
# )


async def generate_image_flux_async(prompt: str) -> str:
    """Asynchronously generate an image using the Together AI API."""
    loop = asyncio.get_running_loop()
    # image_response = client.images.generate(
    try:
        image_response = await loop.run_in_executor(
            executor,
            lambda: client.images.generate(
                prompt=prompt,
                # model="black-forest-labs/FLUX.1-schnell-Free",
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
        # print(f"✅ Image generated successfully: {image_url}")  # ✅ Debugging
        return image_url

    except Exception as e:
        print(f"❌ Image generation failed: {e}")
        return ""  # Return empty string on failure

async def generate_image_flux_free_async(prompt: str) -> str:
    """Asynchronously generate an image using the Together AI API."""
    try:
        response = await async_client.images.generate(
            model="black-forest-labs/FLUX.1-schnell", # tạm đổi vì limit, k free
            # model="black-forest-labs/FLUX.1-dev",
            prompt=prompt,
            steps=12, # max 12
            n=1,
            height=1024,
            width=768,
        )

        if not response or not response.data:
            raise ValueError("Invalid response from Together AI")

        return response.data[0].url
    
    except Exception as e:
        print(f"❌ Image generation failed: {e}")
        return ""  # Return empty string on failure


# async def generate_image_gemini(prompt):
#     """Generate an image using the Gemini AI API and return base64."""
#     loop = asyncio.get_running_loop()
#     try:
#         response = await loop.run_in_executor(executor, lambda: client_gemini.models.generate_images(
#             model='imagen-3.0-generate-002',
#             prompt=prompt,
#             config=types.GenerateImagesConfig(
#                 number_of_images=1,
#                 aspect_ratio="3:4",
#             )
#         ))

#         await asyncio.sleep(10)
#         generated_image = response.generated_images[0]
#         image_bytes = generated_image.image.image_bytes
#         base64_encoded = base64.b64encode(image_bytes).decode("utf-8")
#         return base64_encoded
#     except Exception as e:
#         import traceback
#         print(f"Error in generate_image_gemini: {e}")
#         traceback.print_exc()
#         return None

# async def create_google_cloud_storage_url(base64_image, filename, bucket_name="bucket_comic"):
#     """Uploads base64 image to Google Cloud Storage and returns a public URL."""
#     loop = asyncio.get_running_loop()
#     try:
#         client = storage.Client()
#         bucket = client.bucket(bucket_name)
        
#         blob_name = f"{'testai'}/{filename}"
#         blob = bucket.blob(blob_name)

#         # blob = bucket.blob(filename)

#         image_bytes = base64.b64decode(base64_image)
#         await loop.run_in_executor(executor, lambda: blob.upload_from_file(BytesIO(image_bytes), content_type="image/png"))

#         # Since the bucket is public, we can directly get the public URL
#         return blob.public_url
#     except Exception as e:
#         import traceback
#         print(f"Error in create_google_cloud_storage_url: {e}")
#         traceback.print_exc()
#         return None

# async def generate_and_upload(prompt, prefix="gemini_image_", bucket_name="bucket_comic"):
#     """Combines image generation and uploading to GCS with auto-generated filename."""
#     try:
#         base64_image = await generate_image_gemini(prompt)
#         if base64_image is None:
#             print(f"generate_image_gemini returned None for prompt: {prompt}")
#             return None

#         timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
#         unique_id = uuid.uuid4().hex[:8]
#         filename = f"{prefix}{timestamp}_{unique_id}.png"

#         url = await create_google_cloud_storage_url(base64_image, filename, bucket_name)
#         if url is None:
#             print(f"create_google_cloud_storage_url returned None for filename: {filename}")
#             return None
#         return url
#     except Exception as e:
#         import traceback
#         print(f"Error in generate_and_upload: {e}")
#         traceback.print_exc()
#         return None




# semaphore = asyncio.Semaphore(2)  # ✅ Only 2 image generations at a time

# async def generate_image_gemini_async(prompt):
#     """Generate an image using the Gemini AI API asynchronously and return raw image bytes."""
#     async with semaphore:  # ⏳ Limit to 2 concurrent requests
#         try:
#             await asyncio.sleep(1)  # ⏳ Add 1s delay before processing each request

#             response = await asyncio.to_thread(
#                 lambda: client_gemini.models.generate_images(
#                     model='imagen-3.0-generate-002',
#                     prompt=prompt,
#                     config=types.GenerateImagesConfig(
#                         number_of_images=1,
#                         aspect_ratio="3:4",
#                     )
#                 )
#             )

#             generated_image = response.generated_images[0]
#             return generated_image.image.image_bytes  # ✅ Return raw image bytes
#         except Exception as e:
#             import traceback
#             print(f"Error in generate_image_gemini_async: {e}")
#             traceback.print_exc()
#             return None

    
# async def create_google_cloud_storage_url_async(image_bytes, filename, bucket_name="bucket_comic"):
#     """Uploads raw image bytes to Google Cloud Storage asynchronously and returns a public URL."""
#     loop = asyncio.get_running_loop()
#     try:
#         client = storage.Client()
#         bucket = client.bucket(bucket_name)
#         blob_name = f"testai/{filename}"
#         blob = bucket.blob(blob_name)

#         # ✅ Upload raw bytes directly instead of base64
#         await loop.run_in_executor(None, lambda: blob.upload_from_file(BytesIO(image_bytes), content_type="image/png"))

#         return blob.public_url  # ✅ Return public URL directly
#     except Exception as e:
#         import traceback
#         print(f"Error in create_google_cloud_storage_url_async: {e}")
#         traceback.print_exc()
#         return None

# async def generate_and_upload_async(prompt, prefix="gemini_image_", bucket_name="bucket_comic"):
#     """Generates an image and uploads it asynchronously, returning the public URL."""
#     try:
#         image_bytes = await generate_image_gemini_async(prompt)  # ✅ Limited to 2 at a time
#         if image_bytes is None:
#             print(f"generate_image_gemini_async returned None for prompt: {prompt}")
#             return None

#         timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
#         unique_id = uuid.uuid4().hex[:8]
#         filename = f"{prefix}{timestamp}_{unique_id}.png"

#         # ✅ Upload raw image bytes directly
#         url = await create_google_cloud_storage_url_async(image_bytes, filename, bucket_name)
#         if url is None:
#             print(f"create_google_cloud_storage_url_async returned None for filename: {filename}")
#             return None

#         return url
#     except Exception as e:
#         import traceback
#         print(f"Error in generate_and_upload_async: {e}")
#         traceback.print_exc()
#         return None
# end of comment worked above
    
# async def generate_and_upload_async(prompt, prefix="gemini_image_", bucket_name="bucket_comic"):
#     """Generates an image and uploads it asynchronously."""
#     try:
#         base64_image = await generate_image_gemini_async(prompt)
#         if base64_image is None:
#             print(f"generate_image_gemini_async returned None for prompt: {prompt}")
#             return None

#         timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
#         unique_id = uuid.uuid4().hex[:8]
#         filename = f"{prefix}{timestamp}_{unique_id}.png"

#         # ✅ Upload is fully parallel
#         url = await create_google_cloud_storage_url_async(base64_image, filename, bucket_name)
#         if url is None:
#             print(f"create_google_cloud_storage_url_async returned None for filename: {filename}")
#             return None

#         return url
#     except Exception as e:
#         import traceback
#         print(f"Error in generate_and_upload_async: {e}")
#         traceback.print_exc()
#         return None