"""Old-style OpenAI Python SDK code (v0.28.x). Used for auto-fix tests."""

import openai

openai.api_key = "sk-test-key"

# Old-style chat completion
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello, world!"}]
)

# Old-style completion
response2 = openai.Completion.create(
    model="text-davinci-003",
    prompt="Once upon a time"
)

# Old-style embedding
embedding = openai.Embedding.create(
    model="text-embedding-ada-002",
    input="Hello world"
)

# Old-style image generation
image = openai.Image.create(
    prompt="A cat in space",
    n=1,
    size="1024x1024"
)

# Old-style error handling
try:
    response = openai.ChatCompletion.create(model="gpt-4", messages=[])
except openai.error.RateLimitError:
    print("Rate limited")
except openai.error.AuthenticationError:
    print("Auth error")
