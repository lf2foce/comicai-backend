
from fastapi import HTTPException
from openai import OpenAI
import os
import json
import instructor
from dotenv import load_dotenv
from groq import Groq
from google import genai
from google.genai import types
from google.oauth2 import service_account
from .init_gemini import init_vertexai
# from ..models import Comic, ComicRequest, ComicResponse
from models import ComicScript
from lib.story import system_prompt_v1, system_prompt_v2, system_prompt_v3, system_prompt_v4, system_prompt_v5
# Load environment variables
load_dotenv()

init_vertexai()

openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
groq_client = instructor.from_groq(Groq(), mode=instructor.Mode.JSON)

def openai_text_generation(request):
    # Generate comic script using OpenAI
    try:
        completion = openai.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt_v4},
                {"role": "user", "content": request.prompt}, #"A cyberpunk detective is investigating a missing android in a neon-lit city."
            ],
            response_format=ComicScript,  # Structured Pydantic validation
        )

        # Access the structured response
        comic_data = completion.choices[0].message.parsed
        comic_list = comic_data.model_dump()#['pages']
        # print("============= comic_data parsed", comic_data)
        print(json.dumps(comic_list, indent=2, ensure_ascii=False)) #
        return comic_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI Error: {str(e)}")
    



def groq_text_generation(request):
    try:
        # Generate comic script using Groq
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            # model="llama-3.1-8b-instant",
            response_model=ComicScript,
            messages=[
                {"role": "system", "content": system_prompt_v4},
                {"role": "user", "content": request.prompt},
            ],
            temperature=0.65,
        )

        # Extract structured response
        comic_data = response.model_dump()
        print(json.dumps(comic_data, indent=2, ensure_ascii=False)) #
        # print("============= comic_data parsed", comic_data)
        return comic_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq Error: {str(e)}")
    



def deepseek_text_generation(request):
    try:
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )

        messages = [{"role": "system", "content": system_prompt_v4},
                    {"role": "user", "content": request.prompt}]

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            response_format={
                'type': 'json_object'
            }
        )

        comic_data=json.loads(response.choices[0].message.content)
        print(comic_data)
        return comic_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deepseek Error: {str(e)}")

def gemini_text_generation(request):
    try:
        init_vertexai()
        client = genai.Client(
            vertexai=True,
            project=os.environ.get("PROJECT_ID"),
            location=os.environ.get("LOCATION", "us-central1"),
        )
        # Generate response using Gemini API
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=request.prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': ComicScript,  # Use ComicScript as the expected schema
                'system_instruction': types.Part.from_text(
                    text=system_prompt_v5
                ),
            },
        )
        # Extract structured response
    
        print('======text here', response.text)
        comic_data=json.loads(response.text)
        
        
        return comic_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini API Error: {str(e)}")
