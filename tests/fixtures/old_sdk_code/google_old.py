"""Old-style Google Generative AI code (google-generativeai). Used for auto-fix tests."""

import google.generativeai as genai
from google.generativeai import caching
from google.generativeai import types as old_types

genai.configure(api_key="AIza-test-key")

# Old-style model creation and content generation
model = genai.GenerativeModel("gemini-pro")
response = model.generate_content("Hello, world!")
print(response.text)

# Old-style streaming
for chunk in model.generate_content_stream("Tell me a story"):
    print(chunk.text)

# Old-style caching
cache = caching.CachedContent.create(
    model="gemini-pro",
    display_name="my-cache",
    system_instruction="You are helpful"
)

# Old-style generation config
response2 = model.generate_content(
    "Write a poem",
    generation_config=genai.types.GenerationConfig(
        temperature=0.7,
        max_output_tokens=100
    )
)

# Old-style chat
chat = model.start_chat(history=[])
response3 = chat.send_message("Hello!")
