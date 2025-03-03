import os
import json
import tempfile
from google.oauth2 import service_account
import vertexai

def init_vertexai():
    """Initialize Google Vertex AI with credentials from environment variable.
    Handles issues with private key formatting by writing credentials to a temporary file.
    """
    try:
        # Get the JSON string from environment variable
        credentials_json_str = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if not credentials_json_str:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS_JSON environment variable not set")
        
        # Parse the JSON string to a dictionary
        try:
            credentials_json = json.loads(credentials_json_str)
            print("Successfully parsed credentials JSON")
        except json.JSONDecodeError as e:
            print(f"Failed to parse credentials JSON: {e}")
            raise ValueError(f"Invalid JSON in GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")
        
        # Write the credentials to a temporary file instead of parsing directly
        # This avoids issues with the private key format
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            json.dump(credentials_json, temp_file)
            temp_credentials_path = temp_file.name
            print(f"Wrote credentials to temporary file: {temp_credentials_path}")
        
        # Use the file path for authentication
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_credentials_path
        
        # Initialize Vertex AI
        project_id = os.environ.get("PROJECT_ID")
        location = os.environ.get("LOCATION", "us-central1")
        
        if not project_id:
            raise ValueError("PROJECT_ID environment variable not set")
        
        # Initialize without explicitly passing credentials
        # The library will use GOOGLE_APPLICATION_CREDENTIALS environment variable
        vertexai.init(
            project=project_id,
            location=location
        )
        
        print(f"Successfully initialized Vertex AI for project: {project_id}")
        return True
    except Exception as e:
        print(f"Error initializing Vertex AI: {e}")
        raise e