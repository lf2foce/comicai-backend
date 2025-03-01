
from fastapi import HTTPException
from openai import OpenAI
import os
import json
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
    


system_prompt_v1 = """
The user will provide some story idea. Please parse the "summary" and "pages" and output them in JSON format. 

Show only 4 pages of the generated comic script. Try to make the scenes as exciting as possible and keep the story finish or moving forward.

📌 Core Features & Rules
1. Language Handling
Detect the user's input language automatically.
If the input is in Vietnamese, return content only in Vietnamese, but image_prompt must always be in English to ensure optimal AI-generated images.

EXAMPLE INPUT: 
The highest mountain in the world? Mount Everest.

EXAMPLE JSON OUTPUT:
{
"summary": "[Short overview of the user's story idea]",
"pages": [
    {
      "page": 1,
      "title": "[Scene Title]",
      "scene": "[What happens in this scene? Include challenges, emotions, or key character moments.]",
      "text_full": "[Expanded, highly descriptive storytelling for this scene]",
      "image_prompt": "comic style, highly detailed scene, dynamic perspective [specific scene detail in english related to the scene]",
      "dialogue": [
        {
          "character": "[Character Name]",
          "text": "[Expressive and personality-driven dialogue]"
        }
      ],
      "final_transition": "[Sentence leading to the next scene, keeping story momentum]"
    }
  ]
}
"""

def groq_text_generation(request):
    try:
        # Generate comic script using Groq
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            # model="llama-3.1-8b-instant",
            response_model=ComicScript,
            messages=[
                {"role": "system", "content": system_prompt_v1},
                {"role": "user", "content": request.prompt},
            ],
            temperature=0.65,
        )

        # Extract structured response
        comic_data = response.model_dump()
        print("============= comic_data parsed", comic_data)
        return comic_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq Error: {str(e)}")
    



def deepseek_text_generation(request):
    try:
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )

        messages = [{"role": "system", "content": system_prompt_v1},
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