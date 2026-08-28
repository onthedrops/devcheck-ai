"""Old-style Transformers code (v4.x). Used for auto-fix tests."""

from transformers import AutoModelForCausalLM, AutoFeatureExtractor, AutoModelWithLMHead

# Old-style auth token
model = AutoModelForCausalLM.from_pretrained("bert-base-uncased", use_auth_token="hf_test")

# Old-style feature extractor
extractor = AutoFeatureExtractor.from_pretrained("bert-base-uncased")

# Old-style LM head
model2 = AutoModelWithLMHead.from_pretrained("gpt2")

# Old-style quantization
model3 = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-3.2-3B", load_in_4bit=True)
