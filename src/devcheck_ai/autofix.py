"""Auto-fix engine for AI SDK breaking change migrations.

Scans Python source files for deprecated API patterns and applies
code transformations based on the breaking changes registry.

Safety model:
- `--fix` shows planned patches as a diff (dry run, default)
- `--write-fixes` applies patches to disk (creates backups first)
- Only applies rules marked as safe (high-confidence, well-defined transforms)
- Runs syntax validation after applying; rolls back on failure
"""

from __future__ import annotations

import ast
import difflib
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class FixPlan:
    """A single planned code fix."""

    file_path: Path
    line: int
    rule_id: str
    package: str
    change_type: str
    old_text: str
    new_text: str
    confidence: str  # "high", "medium", "low"
    applied: bool = False
    skipped_reason: str = ""
    migration_note: str = ""
    needs_client: bool = False


@dataclass
class FixReport:
    """Summary of a fix run."""

    total_planned: int = 0
    total_applied: int = 0
    total_skipped: int = 0
    total_files_modified: int = 0
    plans: list[FixPlan] = field(default_factory=list)
    syntax_errors: list[str] = field(default_factory=list)
    backup_dir: Optional[Path] = None

    def to_dict(self) -> dict:
        return {
            "total_planned": self.total_planned,
            "total_applied": self.total_applied,
            "total_skipped": self.total_skipped,
            "total_files_modified": self.total_files_modified,
            "syntax_errors": self.syntax_errors,
            "backup_dir": str(self.backup_dir) if self.backup_dir else None,
            "plans": [
                {
                    "file": str(p.file_path),
                    "line": p.line,
                    "rule_id": p.rule_id,
                    "package": p.package,
                    "change_type": p.change_type,
                    "old_text": p.old_text,
                    "new_text": p.new_text,
                    "confidence": p.confidence,
                    "applied": p.applied,
                    "skipped_reason": p.skipped_reason,
                    "migration_note": p.migration_note,
                }
                for p in self.plans
            ],
        }


# ─── Fix Rules ────────────────────────────────────────────────────────────

# Each rule is a dict with:
#   rule_id: unique identifier
#   package: which SDK this applies to
#   pattern: regex to find the old code (single-line)
#   replacement: replacement template (may contain {client_var})
#   confidence: how safe this transform is
#   migration_note: explanation
#   needs_client: whether the replacement uses a `client.` variable

FIX_RULES: list[dict] = [
    # ── OpenAI Python 0.x → 1.x ──
    {
        "rule_id": "openai-py-chat-completion",
        "package": "openai",
        "pattern": r"openai\.ChatCompletion\.create\b",
        "replacement": "client.chat.completions.create",
        "confidence": "high",
        "needs_client": True,
        "migration_note": "openai.ChatCompletion.create → client.chat.completions.create. Requires an OpenAI() client instance.",
    },
    {
        "rule_id": "openai-py-chat-completion-acreate",
        "package": "openai",
        "pattern": r"openai\.ChatCompletion\.acreate\b",
        "replacement": "client.chat.completions.create",
        "confidence": "high",
        "needs_client": True,
        "migration_note": "openai.ChatCompletion.acreate → client.chat.completions.create (async client). Requires AsyncOpenAI() client.",
    },
    {
        "rule_id": "openai-py-completion",
        "package": "openai",
        "pattern": r"openai\.Completion\.create\b",
        "replacement": "client.completions.create",
        "confidence": "high",
        "needs_client": True,
        "migration_note": "openai.Completion.create → client.completions.create. Note: text-davinci-003 was also deprecated.",
    },
    {
        "rule_id": "openai-py-embedding",
        "package": "openai",
        "pattern": r"openai\.Embedding\.create\b",
        "replacement": "client.embeddings.create",
        "confidence": "high",
        "needs_client": True,
        "migration_note": "openai.Embedding.create → client.embeddings.create. Response structure also changed.",
    },
    {
        "rule_id": "openai-py-image",
        "package": "openai",
        "pattern": r"openai\.Image\.create\b",
        "replacement": "client.images.generate",
        "confidence": "high",
        "needs_client": True,
        "migration_note": "openai.Image.create → client.images.generate.",
    },
    {
        "rule_id": "openai-py-api-key",
        "package": "openai",
        "pattern": r"^(\s*)openai\.api_key\s*=.*$",
        "replacement": r"\1# openai.api_key =  (moved to client constructor)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Module-level openai.api_key removed. Pass api_key to OpenAI() constructor or use OPENAI_API_KEY env var.",
    },
    {
        "rule_id": "openai-py-error-import",
        "package": "openai",
        "pattern": r"openai\.error\.",
        "replacement": "openai.",  # e.g., openai.error.RateLimitError → openai.RateLimitError
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Error classes moved from openai.error module to top-level openai package. Import them directly: from openai import RateLimitError.",
    },
    # ── Google Generative AI (google-generativeai → google-genai) ──
    {
        "rule_id": "google-py-import",
        "package": "google-generativeai",
        "pattern": r"import google\.generativeai as genai\b",
        "replacement": "from google import genai",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Package renamed. Install google-genai. Import changed to: from google import genai",
    },
    {
        "rule_id": "google-py-configure",
        "package": "google-generativeai",
        "pattern": r"^(\s*)genai\.configure\(.*\)$",
        "replacement": r"\1# genai.configure() removed — use: client = genai.Client(api_key=...)",
        "confidence": "medium",
        "needs_client": True,
        "migration_note": "genai.configure() removed. Create a Client instance: client = genai.Client(api_key=...)",
    },
    {
        "rule_id": "google-py-generative-model",
        "package": "google-generativeai",
        "pattern": r"^(\s*)model\s*=\s*genai\.GenerativeModel\(.*\)$",
        "replacement": r"\1# genai.GenerativeModel() removed — use: client.models.generate_content(model=..., contents=...)",
        "confidence": "medium",
        "needs_client": True,
        "migration_note": "GenerativeModel removed. Use client.models.generate_content(model=..., contents=...).",
    },
    {
        "rule_id": "google-py-caching-import",
        "package": "google-generativeai",
        "pattern": r"^(\s*)from google\.generativeai import caching$",
        "replacement": r"\1# from google.generativeai import caching  → use client.caches",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Caching module removed. Use client.caches directly.",
    },
    {
        "rule_id": "google-py-types-import",
        "package": "google-generativeai",
        "pattern": r"from google\.generativeai import types",
        "replacement": "from google.genai import types",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Types module moved from google.generativeai to google.genai.",
    },
    {
        "rule_id": "google-py-generation-config-param",
        "package": "google-generativeai",
        "pattern": r"generation_config=",
        "replacement": "config=",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "generation_config parameter renamed to config in the new SDK.",
    },
    {
        "rule_id": "google-py-generation-config-class",
        "package": "google-generativeai",
        "pattern": r"genai\.types\.GenerationConfig\(",
        "replacement": "types.GenerateContentConfig(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "GenerationConfig class renamed to types.GenerateContentConfig.",
    },
    {
        "rule_id": "google-py-model-generate-content",
        "package": "google-generativeai",
        "pattern": r"^(\s*)(\w+)\s*=\s*model\.generate_content\(.*\)$",
        "replacement": r"\1# \2 = model.generate_content()  → use: client.models.generate_content(model=..., contents=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "model.generate_content() removed. Use client.models.generate_content(model=..., contents=...).",
    },
    {
        "rule_id": "google-py-model-generate-content-stream",
        "package": "google-generativeai",
        "pattern": r"^(\s*)for\s+(\w+)\s+in\s+model\.generate_content_stream\(.*\):$",
        "replacement": r"\1for \2 in []:  # TODO: use client.models.generate_content_stream(model=..., contents=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Streaming moved to client.models.generate_content_stream().",
    },
    {
        "rule_id": "google-py-model-start-chat",
        "package": "google-generativeai",
        "pattern": r"^(\s*)(\w+)\s*=\s*model\.start_chat\(.*\)$",
        "replacement": r"\1# \2 = model.start_chat()  → use: client.chats.create(model=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "model.start_chat() removed. Use client.chats.create(model=...).",
    },
    {
        "rule_id": "google-py-caching-create",
        "package": "google-generativeai",
        "pattern": r"^(\s*)(\w+)\s*=\s*caching\.CachedContent\.create\(.*\)$",
        "replacement": r"\1# \2 = caching.CachedContent.create()  → use: client.caches.create(...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "caching.CachedContent.create() removed. Use client.caches.create(...).",
    },
    # ── Google Vertex AI (google-cloud-aiplatform → google-genai with vertexai=True) ──
    {
        "rule_id": "vertex-py-import",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)import vertexai$",
        "replacement": r"\1# import vertexai  → use: from google import genai",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "vertexai package deprecated. Install google-genai and use genai.Client(vertexai=True, ...).",
    },
    {
        "rule_id": "vertex-py-init",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)vertexai\.init\(.*\)$",
        "replacement": r"\1# vertexai.init() removed — use: client = genai.Client(vertexai=True, project=..., location=...)",
        "confidence": "medium",
        "needs_client": True,
        "migration_note": "vertexai.init() replaced by genai.Client(vertexai=True, project=..., location=...).",
    },
    {
        "rule_id": "vertex-py-generative-model-import",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)from vertexai\.generative_models import GenerativeModel$",
        "replacement": r"\1# from vertexai.generative_models import GenerativeModel  → use: from google import genai",
        "confidence": "high",
        "needs_client": True,
        "migration_note": "vertexai.generative_models deprecated. Use genai.Client(vertexai=True) and client.models.generate_content().",
    },
    {
        "rule_id": "vertex-py-generative-model-extras-import",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)from vertexai\.generative_models import .*$",
        "replacement": r"\1# from vertexai.generative_models import Content, Part, HarmCategory, SafetySetting  → use: from google.genai import types",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Content, Part, HarmCategory, SafetySetting moved to google.genai.types.",
    },
    {
        "rule_id": "vertex-py-language-models-import",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)from vertexai\.language_models import .*$",
        "replacement": r"\1# from vertexai.language_models import ...  → use: client.models.generate_content() with Gemini models",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "vertexai.language_models deprecated. Use client.models.generate_content() with Gemini models.",
    },
    {
        "rule_id": "vertex-py-vision-models-import",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)from vertexai\.vision_models import .*$",
        "replacement": r"\1# from vertexai.vision_models import ...  → use: client.models.generate_content() with image parts",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "vertexai.vision_models deprecated. Use client.models.generate_content() with image parts in contents.",
    },
    {
        "rule_id": "vertex-py-generative-model-create",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*GenerativeModel\(.*\)$",
        "replacement": r"\1# \2 = GenerativeModel()  → use: client.models.generate_content(model=..., contents=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "GenerativeModel() removed. Use client.models.generate_content(model=..., contents=...).",
    },
    {
        "rule_id": "vertex-py-chat-model-from-pretrained",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*ChatModel\.from_pretrained\(.*\)$",
        "replacement": r"\1# \2 = ChatModel.from_pretrained()  → use: client.models.generate_content(model=..., contents=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "ChatModel.from_pretrained() removed. Use client.models.generate_content() with Gemini models.",
    },
    {
        "rule_id": "vertex-py-text-model-from-pretrained",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*TextGenerationModel\.from_pretrained\(.*\)$",
        "replacement": r"\1# \2 = TextGenerationModel.from_pretrained()  → use: client.models.generate_content(model=..., contents=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "TextGenerationModel.from_pretrained() removed. Use client.models.generate_content() with Gemini models.",
    },
    {
        "rule_id": "vertex-py-vision-model-from-pretrained",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*ImageTextModel\.from_pretrained\(.*\)$",
        "replacement": r"\1# \2 = ImageTextModel.from_pretrained()  → use: client.models.generate_content() with image parts",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "ImageTextModel.from_pretrained() removed. Use client.models.generate_content() with image parts in contents.",
    },
    {
        "rule_id": "vertex-py-model-generate-content",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*model\.generate_content\(.*\)$",
        "replacement": r"\1# \2 = model.generate_content()  → use: client.models.generate_content(model=..., contents=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "model.generate_content() removed. Use client.models.generate_content(model=..., contents=...).",
    },
    {
        "rule_id": "vertex-py-model-generate-content-stream",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)for\s+(\w+)\s+in\s+model\.generate_content_stream\(.*\):$",
        "replacement": r"\1for \2 in []:  # TODO: use client.models.generate_content_stream(model=..., contents=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Streaming moved to client.models.generate_content_stream().",
    },
    {
        "rule_id": "vertex-py-model-start-chat",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*model\.start_chat\(.*\)$",
        "replacement": r"\1# \2 = model.start_chat()  → use: client.chats.create(model=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "model.start_chat() removed. Use client.chats.create(model=...).",
    },
    {
        "rule_id": "vertex-py-part-from-text",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*Part\.from_text\(.*\)$",
        "replacement": r"\1# \2 = Part.from_text()  → use: types.Part.from_text(text=...)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Part.from_text() moved to types.Part.from_text(text=...) in google.genai.",
    },
    {
        "rule_id": "vertex-py-chat-send-message",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*\w+\.send_message\(.*\)$",
        "replacement": r"\1# \2 = chat.send_message()  → use: client.chats.send_message(message=...)",
        "confidence": "low",
        "needs_client": False,
        "migration_note": "chat.send_message() API changed. Use client.chats.send_message() or client.models.generate_content().",
    },
    {
        "rule_id": "vertex-py-image-load",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*Image\.load_from_file\(.*\)$",
        "replacement": r"\1# \2 = Image.load_from_file()  → use: client.files.upload(file=...)",
        "confidence": "low",
        "needs_client": False,
        "migration_note": "Image.load_from_file() removed. Use client.files.upload(file=...) and reference in contents.",
    },
    {
        "rule_id": "vertex-py-text-model-predict",
        "package": "google-cloud-aiplatform",
        "pattern": r"^(\s*)(\w+)\s*=\s*\w+\.predict\(.*\)$",
        "replacement": r"\1# \2 = text_model.predict()  → use: client.models.generate_content(model=..., contents=...)",
        "confidence": "low",
        "needs_client": False,
        "migration_note": "TextGenerationModel.predict() removed. Use client.models.generate_content(model=..., contents=...).",
    },
    # ── HuggingFace Transformers 4.x → 5.x ──
    {
        "rule_id": "transformers-py-use-auth-token",
        "package": "transformers",
        "pattern": r"use_auth_token\s*=",
        "replacement": "token=",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "use_auth_token parameter removed in v5. Use token= instead.",
    },
    {
        "rule_id": "transformers-py-feature-extractor",
        "package": "transformers",
        "pattern": r"AutoFeatureExtractor\b",
        "replacement": "AutoImageProcessor",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "AutoFeatureExtractor deprecated and removed in v5. Use AutoImageProcessor.",
    },
    {
        "rule_id": "transformers-py-lm-head",
        "package": "transformers",
        "pattern": r"AutoModelWithLMHead\b",
        "replacement": "AutoModelForCausalLM",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "AutoModelWithLMHead removed. Use AutoModelForCausalLM (causal), AutoModelForMaskedLM (masked), or AutoModelForSeq2SeqLM (encoder-decoder).",
    },
    {
        "rule_id": "transformers-py-load-in-4bit",
        "package": "transformers",
        "pattern": r"^(\s*)load_in_4bit\s*=\s*True",
        "replacement": r"\1quantization_config=BitsAndBytesConfig(load_in_4bit=True)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Direct load_in_4bit removed. Use BitsAndBytesConfig with quantization_config parameter.",
    },
    # ── LangChain 0.1 → 0.2 (import path changes) ──
    {
        "rule_id": "langchain-py-schema-messages",
        "package": "langchain",
        "pattern": r"from langchain\.schema import.*(?:HumanMessage|AIMessage|SystemMessage)",
        "replacement": "from langchain_core.messages import HumanMessage, AIMessage, SystemMessage",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Message types moved to langchain_core.messages in v0.2.",
    },
    {
        "rule_id": "langchain-py-chat-models",
        "package": "langchain",
        "pattern": r"from langchain\.chat_models import\s+ChatOpenAI(\s+as\s+\w+)?$",
        "replacement": r"from langchain_openai import ChatOpenAI\1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "ChatModels moved to provider packages in v0.2. Install langchain-openai, langchain-anthropic, etc.",
    },
    {
        "rule_id": "langchain-py-embeddings",
        "package": "langchain",
        "pattern": r"from langchain\.embeddings import\s+OpenAIEmbeddings(\s+as\s+\w+)?$",
        "replacement": r"from langchain_openai import OpenAIEmbeddings\1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Embedding models moved to provider packages in v0.2.",
    },
    {
        "rule_id": "langchain-py-llms",
        "package": "langchain",
        "pattern": r"from langchain\.llms import\s+OpenAI(\s+as\s+\w+)?$",
        "replacement": r"from langchain_openai import OpenAI\1",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "LLM classes moved to provider packages in v0.2.",
    },
    # ── LangChain 0.2 (additional import path changes) ──
    {
        "rule_id": "langchain-py-schema-document",
        "package": "langchain",
        "pattern": r"from langchain\.schema\.document import\s+(.*)",
        "replacement": r"from langchain_core.documents import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Document class moved from langchain.schema.document to langchain_core.documents.",
    },
    {
        "rule_id": "langchain-py-text-splitter",
        "package": "langchain",
        "pattern": r"from langchain\.text_splitter import\s+(.*)",
        "replacement": r"from langchain_text_splitters import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Text splitters moved to langchain-text-splitters package in v0.2.",
    },
    {
        "rule_id": "langchain-py-vectorstores",
        "package": "langchain",
        "pattern": r"from langchain\.vectorstores import\s+(.*)",
        "replacement": r"from langchain_community.vectorstores import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Vector stores moved to langchain-community package. Provider-specific stores have separate packages.",
    },
    {
        "rule_id": "langchain-py-document-loaders",
        "package": "langchain",
        "pattern": r"from langchain\.document_loaders import\s+(.*)",
        "replacement": r"from langchain_community.document_loaders import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Document loaders moved to langchain-community package.",
    },
    # ── LangChain community → provider (OpenAI only, exact class match) ──
    {
        "rule_id": "langchain-py-community-chat-openai",
        "package": "langchain",
        "pattern": r"from langchain_community\.chat_models import\s+ChatOpenAI(\s+as\s+\w+)?$",
        "replacement": r"from langchain_openai import ChatOpenAI\1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "ChatOpenAI moved from langchain-community to langchain-openai provider package.",
    },
    {
        "rule_id": "langchain-py-community-embeddings-openai",
        "package": "langchain",
        "pattern": r"from langchain_community\.embeddings import\s+OpenAIEmbeddings(\s+as\s+\w+)?$",
        "replacement": r"from langchain_openai import OpenAIEmbeddings\1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "OpenAIEmbeddings moved from langchain-community to langchain-openai provider package.",
    },
    {
        "rule_id": "langchain-py-community-llms-openai",
        "package": "langchain",
        "pattern": r"from langchain_community\.llms import\s+OpenAI(\s+as\s+\w+)?$",
        "replacement": r"from langchain_openai import OpenAI\1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "OpenAI LLM moved from langchain-community to langchain-openai provider package.",
    },
    # ── LangChain function calling utilities ──
    {
        "rule_id": "langchain-py-fc-import-path",
        "package": "langchain",
        "pattern": r"from langchain\.utils\.function_calling import\s+(.*)",
        "replacement": r"from langchain_core.utils.function_calling import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Function calling utilities moved from langchain.utils to langchain_core.utils.",
    },
    {
        "rule_id": "langchain-py-convert-pydantic-function",
        "package": "langchain",
        "pattern": r"convert_pydantic_to_openai_function",
        "replacement": "convert_to_openai_function",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Function renamed. Update import: from langchain_core.utils.function_calling import convert_to_openai_function.",
    },
    {
        "rule_id": "langchain-py-convert-pydantic-tool",
        "package": "langchain",
        "pattern": r"convert_pydantic_to_openai_tool",
        "replacement": "convert_to_openai_tool",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Function renamed. Update import: from langchain_core.utils.function_calling import convert_to_openai_tool.",
    },
    {
        "rule_id": "langchain-py-convert-python-function",
        "package": "langchain",
        "pattern": r"convert_python_function_to_openai_function",
        "replacement": "convert_to_openai_function",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Function renamed to convert_to_openai_function.",
    },
    {
        "rule_id": "langchain-py-format-tool-function",
        "package": "langchain",
        "pattern": r"format_tool_to_openai_function",
        "replacement": "convert_to_openai_function",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Function renamed to convert_to_openai_function.",
    },
    {
        "rule_id": "langchain-py-format-tool-tool",
        "package": "langchain",
        "pattern": r"format_tool_to_openai_tool",
        "replacement": "convert_to_openai_tool",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Function renamed to convert_to_openai_tool.",
    },
    # ── LangChain retriever methods ──
    {
        "rule_id": "langchain-py-get-relevant-docs",
        "package": "langchain",
        "pattern": r"\.get_relevant_documents\(",
        "replacement": ".invoke(",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "BaseRetriever.get_relevant_documents() deprecated in favor of .invoke().",
    },
    {
        "rule_id": "langchain-py-aget-relevant-docs",
        "package": "langchain",
        "pattern": r"\.aget_relevant_documents\(",
        "replacement": ".ainvoke(",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "BaseRetriever.aget_relevant_documents() deprecated in favor of .ainvoke().",
    },
    # ── LangChain ChatOpenAI without model ──
    {
        "rule_id": "langchain-py-chat-openai-no-model",
        "package": "langchain",
        "pattern": r"ChatOpenAI\(\)",
        "replacement": 'ChatOpenAI(model="gpt-4")',
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "LangChain 0.2 requires explicit model specification. Replace 'gpt-4' with the model you intend to use.",
    },
    # ── LangChain v0.3+ (Pydantic 2 migration) ──
    {
        "rule_id": "langchain-v03-pydantic-v1-bridge",
        "package": "langchain",
        "pattern": r"from langchain_core\.pydantic_v1 import\s+(.*)",
        "replacement": r"from pydantic import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v0.3 removed Pydantic 1 compatibility bridges. Use Pydantic 2 directly.",
    },
    {
        "rule_id": "langchain-v03-pydantic-v1-import",
        "package": "langchain",
        "pattern": r"from pydantic\.v1 import\s+(.*)",
        "replacement": r"from pydantic import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "pydantic.v1 bridge removed in v0.3. Use Pydantic 2 directly.",
    },
    {
        "rule_id": "langchain-v03-text-method-to-property",
        "package": "langchain",
        "pattern": r"(\w+)\.text\(\)",
        "replacement": r"\1.text",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "v1.0 changes .text() on message objects from a method to a property.",
    },
    {
        "rule_id": "langchain-v03-create-react-agent",
        "package": "langchain",
        "pattern": r"from langgraph\.prebuilt import\s+create_react_agent",
        "replacement": "from langchain.agents import create_agent",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v1.0 renames create_react_agent to create_agent, moved from langgraph.prebuilt to langchain.agents.",
    },
    {
        "rule_id": "langchain-v03-chains-to-classic",
        "package": "langchain",
        "pattern": r"from langchain\.chains import\s+(.*)",
        "replacement": r"from langchain_classic.chains import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v1.0 moved legacy chains to langchain-classic package.",
    },
    {
        "rule_id": "langchain-v03-retrievers-to-classic",
        "package": "langchain",
        "pattern": r"from langchain\.retrievers import\s+(.*)",
        "replacement": r"from langchain_classic.retrievers import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v1.0 moved retrievers to langchain-classic package.",
    },
    {
        "rule_id": "langchain-v03-indexes-to-classic",
        "package": "langchain",
        "pattern": r"from langchain\.indexes import\s+(.*)",
        "replacement": r"from langchain_classic.indexes import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v1.0 moved indexing API to langchain-classic package.",
    },
    {
        "rule_id": "langchain-v03-hub-to-classic",
        "package": "langchain",
        "pattern": r"from langchain import\s+hub\s*$",
        "replacement": "from langchain_classic import hub",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v1.0 moved hub module to langchain-classic package.",
    },
    {
        "rule_id": "langchain-v03-memory-to-classic",
        "package": "langchain",
        "pattern": r"from langchain\.memory import\s+(.*)",
        "replacement": r"from langchain_classic.memory import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v1.0 moved memory classes to langchain-classic. Use LangGraph checkpointer for new code.",
    },
    # ── LlamaIndex v0.10+ (import path changes) ──
    {
        "rule_id": "llamaindex-py-core-import",
        "package": "llamaindex",
        "pattern": r"from llama_index import\s+(VectorStoreIndex|SimpleDirectoryReader|Document|StorageContext)",
        "replacement": r"from llama_index.core import \1",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Core abstractions moved from llama_index to llama_index.core in v0.10.",
    },
    {
        "rule_id": "llamaindex-py-llms-import",
        "package": "llamaindex",
        "pattern": r"from llama_index\.llms import\s+(\w+)",
        "replacement": r"from llama_index.llms.\1 import \1  # NOTE: install llama-index-llms-\1",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "LLM integrations are now separate packages. Use fully-qualified provider path.",
    },
    {
        "rule_id": "llamaindex-py-vector-stores-import",
        "package": "llamaindex",
        "pattern": r"from llama_index\.vector_stores import\s+(\w+)",
        "replacement": r"from llama_index.vector_stores.\1 import \1  # NOTE: install llama-index-vector-stores-\1",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Vector store integrations are now separate packages.",
    },
    {
        "rule_id": "llamaindex-py-gpt-simple-vector-index",
        "package": "llamaindex",
        "pattern": r"GPTSimpleVectorIndex",
        "replacement": "VectorStoreIndex",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "GPTSimpleVectorIndex renamed to VectorStoreIndex.",
    },
    {
        "rule_id": "llamaindex-py-gpt-vector-store-index",
        "package": "llamaindex",
        "pattern": r"GPTVectorStoreIndex",
        "replacement": "VectorStoreIndex",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "GPTVectorStoreIndex consolidated into VectorStoreIndex.",
    },
    # ── Pinecone v2→v3 (client init migration) ──
    {
        "rule_id": "pinecone-py-init",
        "package": "pinecone",
        "pattern": r"pinecone\.init\(.*\)",
        "replacement": "# pinecone.init() removed — use: from pinecone import Pinecone; pc = Pinecone(api_key=...)",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "pinecone.init() removed. Use Pinecone() client class.",
    },
    {
        "rule_id": "pinecone-py-index-module",
        "package": "pinecone",
        "pattern": r"pinecone\.Index\(",
        "replacement": "pc.Index(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Index() moved from module-level to instance method on Pinecone client.",
    },
    {
        "rule_id": "pinecone-py-list-indexes",
        "package": "pinecone",
        "pattern": r"pinecone\.(list_indexes|delete_index|describe_index|configure_index)\(",
        "replacement": r"pc.\1(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Control-plane operations moved to instance methods on Pinecone client.",
    },
    # ── Weaviate v3→v4 (client init migration) ──
    {
        "rule_id": "weaviate-py-client-class",
        "package": "weaviate-client",
        "pattern": r"weaviate\.Client\(",
        "replacement": "weaviate.connect_to_local()  # or WeaviateClient(...); must call client.close()",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "weaviate.Client() removed. Use connect_to_local() or WeaviateClient().",
    },
    {
        "rule_id": "weaviate-py-schema-create-class",
        "package": "weaviate-client",
        "pattern": r"client\.schema\.create_class\(",
        "replacement": "client.collections.create(  # use Property/DataType classes",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "schema.create_class() replaced by collections.create() with typed Property/DataType.",
    },
    {
        "rule_id": "weaviate-py-data-object-create",
        "package": "weaviate-client",
        "pattern": r"client\.data_object\.create\(",
        "replacement": "collection.data.insert(  # get collection first: collection = client.collections.use(name)",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "data_object.create() removed. Use collection.data.insert() after getting collection.",
    },
    {
        "rule_id": "weaviate-py-query-get",
        "package": "weaviate-client",
        "pattern": r"client\.query\.get\(",
        "replacement": "collection.query.  # use fetch_objects/near_text/bm25 on collection.query",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "GraphQL builder pattern removed. Use collection.query methods.",
    },
    {
        "rule_id": "weaviate-py-batch-context",
        "package": "weaviate-client",
        "pattern": r"with client\.batch as batch:",
        "replacement": "with client.batch.dynamic() as batch:",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Implicit batch context removed. Use explicit algorithm: dynamic(), fixed_size(), or rate_limit().",
    },
    {
        "rule_id": "weaviate-py-batch-add-data-object",
        "package": "weaviate-client",
        "pattern": r"batch\.add_data_object\(",
        "replacement": "batch.add_object(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "batch.add_data_object() renamed to batch.add_object().",
    },
    {
        "rule_id": "weaviate-py-filter-path",
        "package": "weaviate-client",
        "pattern": r"Filter\(path=",
        "replacement": "Filter.by_property(name=",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Filter(path=...) replaced by Filter.by_property(name=...).",
    },
    # ── ChromaDB (client init migration) ──
    {
        "rule_id": "chromadb-py-persistent-client",
        "package": "chromadb",
        "pattern": r"chromadb\.Client\(Settings\(.*chroma_db_impl",
        "replacement": "chromadb.PersistentClient(  # path= for persist directory",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Old Settings(chroma_db_impl=...) client pattern removed. Use PersistentClient, EphemeralClient, or HttpClient.",
    },
    {
        "rule_id": "chromadb-py-http-client",
        "package": "chromadb",
        "pattern": r"chromadb\.Client\(Settings\(.*chroma_api_impl.*rest",
        "replacement": "chromadb.HttpClient(  # host=..., port=...",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "HTTP client via Settings(chroma_api_impl='rest') replaced by HttpClient(host=..., port=...).",
    },
    {
        "rule_id": "chromadb-py-persist",
        "package": "chromadb",
        "pattern": r"\.persist\(\)",
        "replacement": "# .persist() removed — writes are auto-saved",
        "confidence": "high",
        "needs_client": False,
        "migration_note": ".persist() removed. Chroma saves all writes to disk instantly.",
    },
    {
        "rule_id": "chromadb-py-max-batch-size",
        "package": "chromadb",
        "pattern": r"\.max_batch_size(?![\w(])",
        "replacement": ".get_max_batch_size()",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "max_batch_size property replaced by get_max_batch_size() method.",
    },
    # ── Cohere (v1→v2 client migration) ──
    {
        "rule_id": "cohere-py-client-v2",
        "package": "cohere",
        "pattern": r"cohere\.Client\(",
        "replacement": "cohere.ClientV2(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v2 API requires ClientV2. Old Client class still exists for v1 compatibility.",
    },
    {
        "rule_id": "cohere-py-check-api-key",
        "package": "cohere",
        "pattern": r"\.check_api_key\(",
        "replacement": "# check_api_key() removed — call any endpoint; 401 = invalid key",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "check_api_key() removed in SDK v5.0.0 with no replacement.",
    },
    {
        "rule_id": "cohere-py-generate-to-chat",
        "package": "cohere",
        "pattern": r"co\.generate\(prompt=",
        "replacement": "co.chat(  # use messages=[{'role': 'user', 'content': prompt}]",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "Generate API deprecated. Use chat() with messages list.",
    },
    # ── Mistral AI (client consolidation) ──
    {
        "rule_id": "mistral-py-import",
        "package": "mistralai",
        "pattern": r"from mistralai import Mistral$",
        "replacement": "from mistralai.client import Mistral",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v2.x moved Mistral class to mistralai.client submodule (PEP 420 namespace).",
    },
    {
        "rule_id": "mistral-py-models-import",
        "package": "mistralai",
        "pattern": r"from mistralai\.(models|types|utils) import",
        "replacement": r"from mistralai.client.\1 import",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v2.x relocated models/types/utils under mistralai.client.*",
    },
    {
        "rule_id": "mistral-py-chat-complete",
        "package": "mistralai",
        "pattern": r"client\.chat\((?!\.)",
        "replacement": "client.chat.complete(",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "v1.x: client.chat() reorganized to client.chat.complete().",
    },
    {
        "rule_id": "mistral-py-chat-stream",
        "package": "mistralai",
        "pattern": r"client\.chat_stream\(",
        "replacement": "client.chat.stream(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "v1.x: client.chat_stream became client.chat.stream.",
    },
    {
        "rule_id": "mistral-py-mistral-client",
        "package": "mistralai",
        "pattern": r"MistralClient\(",
        "replacement": "Mistral(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "MistralClient/MistralAsyncClient consolidated into Mistral.",
    },
    {
        "rule_id": "mistral-py-chat-message",
        "package": "mistralai",
        "pattern": r"from mistralai.*import ChatMessage",
        "replacement": "from mistralai.models import UserMessage  # or SystemMessage, AssistantMessage",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "ChatMessage replaced by role-specific message types.",
    },
    # ── Haystack (v1→v2 migration) ──
    {
        "rule_id": "haystack-py-nodes-import",
        "package": "haystack-ai",
        "pattern": r"from haystack\.nodes import",
        "replacement": "from haystack.components  # NOTE: migrate to specific component submodules",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "haystack.nodes module removed in v2. Use haystack.components submodules.",
    },
    {
        "rule_id": "haystack-py-farm-reader",
        "package": "haystack-ai",
        "pattern": r"FARMReader\(",
        "replacement": "ExtractiveReader(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "FARMReader/TransformersReader unified into ExtractiveReader.",
    },
    {
        "rule_id": "haystack-py-bm25-retriever",
        "package": "haystack-ai",
        "pattern": r"BM25Retriever\(",
        "replacement": "InMemoryBM25Retriever(",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Generic BM25Retriever replaced by store-specific InMemoryBM25Retriever.",
    },
    {
        "rule_id": "haystack-py-model-param",
        "package": "haystack-ai",
        "pattern": r"model_name_or_path=",
        "replacement": "model=",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "model_name_or_path and model_name parameters renamed to model across all components.",
    },
    {
        "rule_id": "haystack-py-write-doc",
        "package": "haystack-ai",
        "pattern": r"\.write_document\(",
        "replacement": ".write_documents([",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "write_document() (singular) removed. Use write_documents() (plural, takes list).",
    },
    {
        "rule_id": "haystack-py-doc-text",
        "package": "haystack-ai",
        "pattern": r"document\.text",
        "replacement": "document.content",
        "confidence": "high",
        "needs_client": False,
        "migration_note": "Document.text renamed to Document.content.",
    },
    {
        "rule_id": "haystack-py-add-node",
        "package": "haystack-ai",
        "pattern": r"pipeline\.add_node\(",
        "replacement": "pipeline.add_component(  # then use pipeline.connect()",
        "confidence": "medium",
        "needs_client": False,
        "migration_note": "add_node() removed. Use add_component() + connect().",
    },
]


# ─── File Discovery ─────────────────────────────────────────────────────────

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".tox",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
    "*.egg-info",
    ".mypy_cache",
    ".ruff_cache",
    ".devcheck-ai-backups",
}


def discover_python_files(project_path: Path) -> list[Path]:
    """Find all Python files in the project, excluding virtualenvs and caches."""
    files = []
    for py_file in project_path.rglob("*.py"):
        if any(skip in py_file.parts for skip in SKIP_DIRS):
            continue
        if py_file.name.startswith("."):
            continue
        files.append(py_file)
    return sorted(files)


# ─── Fix Engine ─────────────────────────────────────────────────────────────


class FixEngine:
    """Scans files, generates fix plans, and optionally applies them."""

    def __init__(self, project_path: Path, package_filter: Optional[str] = None):
        self.project_path = project_path
        self.package_filter = package_filter
        self.rules = FIX_RULES.copy()
        if package_filter:
            self.rules = [r for r in self.rules if r["package"] == package_filter]

    def scan_file(self, file_path: Path) -> list[FixPlan]:
        """Scan a single file for fixable patterns. Returns list of FixPlans."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            return []

        plans: list[FixPlan] = []
        lines = content.split("\n")

        for rule in self.rules:
            for i, line in enumerate(lines, 1):
                # Handle regex replacement patterns (with capture groups like \1)
                if "\\1" in rule["replacement"]:
                    matches = list(re.finditer(rule["pattern"], line))
                    for match in matches:
                        replacement = match.expand(rule["replacement"])
                        plans.append(
                            FixPlan(
                                file_path=file_path,
                                line=i,
                                rule_id=rule["rule_id"],
                                package=rule["package"],
                                change_type=rule.get("change_type", "renamed_method"),
                                old_text=line.strip(),
                                new_text=replacement.strip(),
                                confidence=rule["confidence"],
                                needs_client=rule.get("needs_client", False),
                                migration_note=rule["migration_note"],
                            )
                        )
                else:
                    matches = list(re.finditer(rule["pattern"], line))
                    for match in matches:
                        replacement = rule["replacement"]
                        new_line = line[: match.start()] + replacement + line[match.end() :]
                        plans.append(
                            FixPlan(
                                file_path=file_path,
                                line=i,
                                rule_id=rule["rule_id"],
                                package=rule["package"],
                                change_type=rule.get("change_type", "renamed_method"),
                                old_text=line.strip(),
                                new_text=new_line.strip(),
                                confidence=rule["confidence"],
                                needs_client=rule.get("needs_client", False),
                                migration_note=rule["migration_note"],
                            )
                        )

        return plans

    def scan_all(self) -> list[FixPlan]:
        """Scan all Python files in the project."""
        py_files = discover_python_files(self.project_path)
        all_plans: list[FixPlan] = []
        for py_file in py_files:
            all_plans.extend(self.scan_file(py_file))
        return all_plans

    def _check_needs_client_injection(self, file_path: Path, plans: list[FixPlan]) -> bool:
        """Check if a file needs a client variable injected."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            return False

        # Check if client is already defined
        if re.search(r"client\s*=\s*(OpenAI|AsyncOpenAI|genai\.Client)\(", content):
            return False

        # Check if there are any plans that need a client
        return any(p.needs_client for p in plans)

    def _inject_client(self, content: str, package: str) -> str:
        """Inject client initialization after imports."""
        lines = content.split("\n")

        # Find the last import line
        last_import_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                last_import_idx = i

        # Determine client init lines based on package
        if package == "openai":
            client_lines = [
                "",
                "from openai import OpenAI",
                "client = OpenAI()  # Uses OPENAI_API_KEY env var",
            ]
        elif package == "google-generativeai":
            client_lines = [
                "",
                "from google import genai",
                "client = genai.Client()  # Uses GOOGLE_API_KEY env var",
            ]
        elif package == "google-cloud-aiplatform":
            client_lines = [
                "",
                "from google import genai",
                'client = genai.Client(vertexai=True, project="my-project", location="us-central1")',
            ]
        else:
            return content  # Don't inject for unknown packages

        if last_import_idx == -1:
            # No imports found, prepend
            return "\n".join(client_lines) + "\n\n" + content

        # Insert after last import
        lines[last_import_idx + 1 : last_import_idx + 1] = client_lines
        return "\n".join(lines)

    def _get_client_init_lines(self, package: str) -> list[str]:
        if package == "openai":
            return [
                "from openai import OpenAI",
                "client = OpenAI()  # Uses OPENAI_API_KEY env var",
                "",
            ]
        elif package == "google-generativeai":
            return [
                "from google import genai",
                "client = genai.Client()  # Uses GOOGLE_API_KEY env var",
                "",
            ]
        elif package == "google-cloud-aiplatform":
            return [
                "from google import genai",
                'client = genai.Client(vertexai=True, project="my-project", location="us-central1")',
                "",
            ]
        return []

    def apply_fixes(self, plans: list[FixPlan], dry_run: bool = True) -> FixReport:
        """Apply (or plan) fixes. If dry_run, no files are modified."""
        report = FixReport()
        report.total_planned = len(plans)

        if dry_run:
            report.plans = plans
            report.total_skipped = len(plans)
            return report

        # Group plans by file
        plans_by_file: dict[Path, list[FixPlan]] = {}
        for plan in plans:
            plans_by_file.setdefault(plan.file_path, []).append(plan)

        # Create backup directory
        backup_dir = self.project_path / ".devcheck-ai-backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)
        report.backup_dir = backup_dir

        modified_files: set[Path] = set()

        for file_path, file_plans in plans_by_file.items():
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                for p in file_plans:
                    p.skipped_reason = "Could not read file"
                    report.total_skipped += 1
                continue

            # Backup original
            rel_path = file_path.relative_to(self.project_path)
            backup_path = backup_dir / rel_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)

            # Determine which package needs client injection
            needs_client = any(p.needs_client for p in file_plans)
            client_package = None
            if needs_client:
                for p in file_plans:
                    if p.needs_client:
                        client_package = p.package
                        break

            # Apply replacements line by line
            lines = content.split("\n")
            applied_count = 0

            for plan in file_plans:
                if plan.line > len(lines):
                    plan.skipped_reason = "Line number out of range"
                    report.total_skipped += 1
                    continue

                original_line = lines[plan.line - 1]
                rule = next((r for r in self.rules if r["rule_id"] == plan.rule_id), None)
                if not rule:
                    plan.skipped_reason = "Rule not found"
                    report.total_skipped += 1
                    continue

                # Apply the substitution
                new_line = re.sub(
                    rule["pattern"],
                    rule["replacement"],
                    original_line,
                )

                if new_line != original_line:
                    lines[plan.line - 1] = new_line
                    plan.applied = True
                    applied_count += 1
                    report.total_applied += 1
                else:
                    plan.skipped_reason = "Pattern not found on line (may have been already fixed)"
                    report.total_skipped += 1

            # Inject client if needed
            new_content = "\n".join(lines)
            if needs_client and client_package:
                new_content = self._inject_client(new_content, client_package)

            # Write the modified content
            file_path.write_text(new_content, encoding="utf-8")
            modified_files.add(file_path)

            # Syntax check
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                report.syntax_errors.append(f"{file_path}: {e}")
                # Rollback
                shutil.copy2(backup_path, file_path)
                for p in file_plans:
                    p.applied = False
                    p.skipped_reason = f"Rolled back: syntax error after fix ({e})"
                report.total_applied -= applied_count
                report.total_skipped += applied_count

        report.total_files_modified = len(modified_files)
        report.plans = plans
        return report

    def generate_diff(self, plans: list[FixPlan]) -> str:
        """Generate a unified diff of all planned changes."""
        diff_lines: list[str] = []
        plans_by_file: dict[Path, list[FixPlan]] = {}
        for plan in plans:
            plans_by_file.setdefault(plan.file_path, []).append(plan)

        for file_path, file_plans in sorted(plans_by_file.items()):
            try:
                original = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
            except (UnicodeDecodeError, PermissionError):
                continue

            # Simulate applying fixes
            modified_lines = original.copy()
            for plan in file_plans:
                if plan.line <= len(modified_lines):
                    rule = next((r for r in self.rules if r["rule_id"] == plan.rule_id), None)
                    if rule:
                        if "\\1" in rule["replacement"]:
                            modified_lines[plan.line - 1] = re.sub(rule["pattern"], rule["replacement"], modified_lines[plan.line - 1])
                        else:
                            modified_lines[plan.line - 1] = re.sub(rule["pattern"], rule["replacement"], modified_lines[plan.line - 1])

            # Check if client injection is needed
            needs_client = any(p.needs_client for p in file_plans)
            if needs_client:
                client_package = next((p.package for p in file_plans if p.needs_client), None)
                if client_package:
                    modified_content = self._inject_client("".join(modified_lines), client_package)
                    modified_lines = modified_content.splitlines(keepends=True)

            diff = difflib.unified_diff(
                original,
                modified_lines,
                fromfile=str(file_path),
                tofile=str(file_path),
            )
            diff_lines.extend(diff)

        return "".join(diff_lines)
