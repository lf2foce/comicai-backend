
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
from lib.story import system_prompt_v1, system_prompt_v2, system_prompt_v3, system_prompt_v4, system_prompt_v5, system_prompt_v5_continue
# Load environment variables
load_dotenv()



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

def gemini_text_generation_new(prompt):
    try:
        
        client = genai.Client(
            vertexai=True,
            project=os.environ.get("PROJECT_ID"),
            location=os.environ.get("LOCATION", "us-central1"),
        )
        # Generate response using Gemini API
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': ComicScript,  # Use ComicScript as the expected schema
                'system_instruction': types.Part.from_text(
                    text=system_prompt_v5_continue
                ),
            },
        )
        # Extract structured response
    
        print('======text here', response.text)
        comic_data=json.loads(response.text)
        
        
        return comic_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini API Error: {str(e)}")

import re
# Function to ensure character descriptions remain consistent in new `image_prompt`
def ensure_character_consistency(image_prompt, character_descriptions):
    """
    Replaces character names in an image_prompt with their full descriptions for visual consistency.
    """
    for char in character_descriptions:
        name = char["name"]
        full_description = f"Character: {name}, {char['description']}"
        image_prompt = re.sub(fr"Character:\s*{re.escape(name)}\b", full_description, image_prompt)

    return image_prompt
# Extract unique character descriptions from previous pages' image_prompts
def extract_character_descriptions(previous_pages):
    """
    Extracts character descriptions from previous pages' image_prompts to ensure consistency.
    """
    character_descriptions = {}

    for page in previous_pages:
        if "image_prompt" in page:
            matches = re.findall(r"Character:\s*([^,]+),\s*(.*?)(?=\s*\|\s*|$)", page["image_prompt"])
            for name, description in matches:
                character_descriptions[name.strip()] = {
                    "name": name.strip(),
                    "description": description.strip()
                }

    return list(character_descriptions.values())

def generate_new_comic_pages(previous_pages, num_pages=3):
    """Generate multiple new comic pages using AI with full context."""
    
    # Extract previous story in a structured format
    previous_story = "\n\n".join([
        f"Page {i+1}: {page['scene']}\n"
        f"Full Text: {page['text_full']}\n"
        f"Dialogue: " + " | ".join([f"{d['character']}: {d['text']}" for d in page.get('dialogue', [])]) + "\n"
        f"Final Transition: {page['final_transition']}"
        for i, page in enumerate(previous_pages)
    ])

    # Get characters with their exact descriptions
    characters = extract_character_descriptions(previous_pages)

    # Generate the prompt for story continuation
    prompt = f"""
    {{
    "task": "Continue the existing comic story while maintaining full character, art style, and narrative consistency.",
    "previous_story": "{previous_story}",
    "characters": {characters},
    "num_pages": "{num_pages}",
    "requirements": {{
        "language": "Follow the language of the previous story. If in Vietnamese, keep `image_prompt` and `characters` in English.",
        "art_style": "Maintain the exact same art style as previous pages (e.g., cartoon style, anime style).",
        "scene_progression": "Ensure smooth and logical story progression.",
        "image_prompt_structure": "Strictly reuse character descriptions in all `image_prompt`s to maintain visual consistency.",
        "dialogue": "Keep character interactions expressive and engaging.",
        "image_prompt_character_consistency": "For every `image_prompt`, replace any character mention with their full description. Use the following format: `Character: [Name], [Exact Description]`, followed by scene-specific actions.",
        "example_image_prompt": "cartoon style | Scene: Bắp soaring through the sky, dodging a playful gust of wind | Character: Bắp, a small, cheerful green dragon with big blue eyes and tiny wings, happily flapping its tiny wings | Perspective: dynamic mid-air shot | Mood: adventurous, lighthearted"
    }}
    }}
    """

    print('==========starting new comic generation \n')
    # Convert AI response to structured JSON
    new_scenes = gemini_text_generation_new(prompt)['pages']
 
    return new_scenes