"""Old-style Vertex AI SDK code (google-cloud-aiplatform). Used for auto-fix tests."""

import vertexai
from vertexai.generative_models import GenerativeModel, Content, Part, HarmCategory, SafetySetting
from vertexai.language_models import ChatModel, TextGenerationModel
from vertexai.vision_models import ImageTextModel, Image

vertexai.init(project="my-project", location="us-central1")

# Old-style generative model
model = GenerativeModel("gemini-1.5-pro")
response = model.generate_content("Hello, world!")
print(response.text)

# Old-style streaming with GenerativeModel
for chunk in model.generate_content_stream("Tell me a story"):
    print(chunk.text)

# Old-style chat
chat = model.start_chat()
response2 = chat.send_message("Hello!")

# Old-style ChatModel
chat_model = ChatModel.from_pretrained("chat-bison")
chat2 = chat_model.start_chat()
response3 = chat2.send_message("Hi there")

# Old-style TextGenerationModel
text_model = TextGenerationModel.from_pretrained("text-bison")
response4 = text_model.predict("Write a summary")

# Old-style vision model
vision_model = ImageTextModel.from_pretrained("imagetext")
image = Image.load_from_file("photo.jpg")
response5 = vision_model.get_captions(image)

# Old-style Part construction
part = Part.from_text("Hello")
content = Content(parts=[part], role="user")

# Old-style safety settings
safety = SafetySetting(
    category=HarmCategory.HARM_CATEGORY_HARASSMENT,
    threshold=HarmCategory.HarmBlockThreshold.BLOCK_NONE
)
