import google.generativeai as genai
import os
from dotenv import load_dotenv
from PIL import Image
import io
import base64

load_dotenv(dotenv_path=".env.google")

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


class GeminiUtil:
    def __init__(self):
        self.model = genai.GenerativeModel("gemini-2.5-flash-image-preview")

    def generate_image(
        self,
        image_prompt: str,
        base_image_path: str,
        model_name: str = "gemini-2.5-flash-image-preview",
    ):
        try:
            img = Image.open(base_image_path)
            response = self.model.generate_content([image_prompt, img])

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    return base64.b64encode(image_bytes).decode("utf-8")
            return None
        except Exception as e:
            print(f"Error generating image: {e}")
            return None
