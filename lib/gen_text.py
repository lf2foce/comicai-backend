from fastapi import HTTPException
# from openai import OpenAI
import os
import instructor
from dotenv import load_dotenv
from groq import Groq
# from ..models import Comic, ComicRequest, ComicResponse
from models import ComicScript

# Load environment variables
load_dotenv()

# openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
groq_client = instructor.from_groq(Groq(), mode=instructor.Mode.JSON)

# def openai_text_generation(request):
#     # Generate comic script using OpenAI
#     try:
#         completion = openai.beta.chat.completions.parse(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "You are a professional comic book creator. Generate a detailed 4 pages comic script based on the user's prompt. The response must be a JSON object following this structure:\n"
#                                             "- 'pages': A list of pages.\n"
#                                             "- Each page includes:\n"
#                                             "  - 'scene': A vivid description of the visual setting.\n"
#                                             "  - 'dialogue': A list of dictionaries where each dictionary contains 'character' and 'text' fields.\n"
#                                             "Ensure a coherent storyline across pages. Content should be in the language of the story."},
#                 {"role": "user", "content": request.prompt}, #"A cyberpunk detective is investigating a missing android in a neon-lit city."
#             ],
#             response_format=ComicScript,  # Structured Pydantic validation
#         )

#         # Access the structured response
#         comic_data = completion.choices[0].message.parsed

#         comic_list = comic_data.model_dump()['pages']
#         # print("============= comic_data parsed", comic_data)

#         return comic_list
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"OpenAI Error: {str(e)}")
    

def groq_text_generation(request):
    try:
        # Generate comic script using Groq
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            # model="llama-3.1-8b-instant",
            response_model=ComicScript,
            messages=[
                {"role": "system", "content": "You are a professional comic book creator. Generate a detailed 4-page comic script based on the user's prompt. The response must be a JSON object following this structure:\n"
                                                "- 'pages': A list of pages.\n"
                                                "- Each page includes:\n"
                                                "  - 'scene': A vivid description of the visual setting.\n"
                                                "  - 'dialogue': A list of dictionaries where each dictionary contains 'character' and 'text' fields.\n"
                                                "Ensure a coherent storyline across pages. Content should be in the language of the story. Keep only scene in English and make it can easier for ai image generation"},
                {"role": "user", "content": request.prompt},
            ],
            temperature=0.65,
        )

        # Extract structured response
        comic_data = response.model_dump()
        print("============= comic_data parsed", comic_data)
        return comic_data['pages']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq Error: {str(e)}")