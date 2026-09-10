# devcheck-ai

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/onthedrops/devcheck-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/onthedrops/devcheck-ai/actions/workflows/ci.yml)
[![Fix Rules](https://img.shields.io/badge/auto--fix-103%20rules%20%7C%2012%20SDKs-blue)](https://github.com/onthedrops/devcheck-ai)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)
[![PyPI](https://img.shields.io/pypi/v/devcheck-ai)](https://pypi.org/project/devcheck-ai/)

**Preflight dependency reality check for AI-generated code.**

When AI assistants write code, they may use libraries and APIs from their training data that are now outdated, deprecated, or have shipped breaking changes. `devcheck-ai` scans your project's dependency manifests, checks each one against its live registry (PyPI, npm), and reports version drift, deprecations, and risk levels — **before** you ship broken code.

## The Problem

AI coding assistants (including this one) have a knowledge cutoff. The AI ecosystem moves fast:

- OpenAI shipped breaking changes between `openai` v0.28 and v1.0
- Anthropic's SDK changed method signatures across major versions
- LangChain restructured into `langchain-core`, `langchain-openai`, etc.
- npm packages get deprecated, yanked, or replaced

Without a preflight check, AI-generated code may reference APIs that no longer exist.

## What It Does

- **Detects version drift** — Compares your pinned versions against the latest registry versions
- **Flags deprecated packages** — Both PyPI and npm deprecation notices
- **Detects yanked versions** — Versions pulled from registries for security/safety
- **Identifies unmaintained packages** — No release in 2+ years (npm)
- **Risk scoring** — Low (patch) / Medium (minor) / High (major) / Critical (deprecated)
- **Smoke testing** — Optionally installs and imports packages in an isolated environment
- **Breaking changes registry** — Cross-references the [ai-sdk-breakage-registry](https://github.com/onthedrops/ai-sdk-breakage-registry) to show exactly what broke and how to fix it

## Install

```bash
pip install devcheck-ai
```

Or from source:

```bash
git clone https://github.com/onthedrops/devcheck-ai.git
cd devcheck-ai
pip install -e .
```

## Quick Start

```bash
# Scan a project for outdated deps and breaking changes
devcheck-ai ./my-project

# Preview auto-fixes without changing files
devcheck-ai ./my-project --fix

# Apply fixes (creates backups automatically)
devcheck-ai ./my-project --write-fixes
```
- **Auto-fix mode** — Scans source files and rewrites deprecated API calls automatically. Dry-run diff by default, with backup-protected `--write-fixes` mode
- **Multiple output formats** — CLI table, JSON, Markdown report
- **CI-ready** — Exit codes for version drift (`--fail-on drift`) or breaking changes (`--fail-on breaking`)

## Usage

```bash
# Get JSON output for CI
devcheck-ai ./my-project --format json -o report.json

# Run smoke tests on high-risk dependencies
devcheck-ai ./my-project --smoke --show-urls

# Check against AI SDK breaking changes registry
devcheck-ai ./my-project --breaking-changes

# Preview auto-fixes as a diff (dry run, no files modified)
devcheck-ai ./my-project --fix

# Apply auto-fixes (creates backups in .devcheck-ai-backups/ first)
devcheck-ai ./my-project --write-fixes

# Fix only a specific package
devcheck-ai ./my-project --write-fixes --fix-package openai

# Only fail on critical issues
devcheck-ai ./my-project --fail-on critical
```

## Auto-Fix Coverage

The `--fix` and `--write-fixes` flags scan Python source files for deprecated SDK patterns and apply safe, regex-based migrations. Each fix includes a migration note and creates backups before modifying files.

| Package | Fix Rules | What it covers |
|---------|-----------|----------------|
| `openai` | 7 | `ChatCompletion.create` → client-based API, `Embedding.create`, `Image.create`, `api_key`, `error.*` classes |
| `google-generativeai` | 11 | `genai.configure()` → `Client()`, `GenerativeModel` removal, `GenerationConfig` rename, streaming, caching, chat |
| `google-cloud-aiplatform` | 15 | `vertexai.init()`, `generative_models`, `language_models`, `vision_models`, `Part.from_text`, `Image.load_from_file` |
| `transformers` | 4 | `AutoFeatureExtractor` → `AutoImageProcessor`, `AutoModelWithLMHead` → `AutoModelForCausalLM`, `use_auth_token` → `token` |
| `langchain` (v0.2) | 20 | Import paths (`schema`, `chat_models`, `embeddings`, `llms`, `text_splitter`, `vectorstores`, `document_loaders`), community → provider, function-calling renames, retriever methods, `ChatOpenAI()` no-model |
| `langchain` (v0.3+) | 9 | Pydantic v1 bridges, `.text()` → `.text`, `create_react_agent` → `create_agent`, chains/retrievers/indexes/hub/memory → `langchain-classic` |
| `llamaindex` | 5 | `from llama_index import` → `llama_index.core`, `llms`/`vector_stores` provider paths, `GPTSimpleVectorIndex` → `VectorStoreIndex` |
| `pinecone` | 3 | `pinecone.init()` removal, `pinecone.Index()` → `pc.Index()`, control-plane ops → instance methods |
| `weaviate-client` | 7 | `weaviate.Client()` → `connect_to_local()`, `schema.create_class` → `collections.create`, `query.get` → `collection.query`, batch API, `Filter(path=)` → `Filter.by_property(name=)` |
| `chromadb` | 4 | `Client(Settings(...))` → `PersistentClient`/`HttpClient`, `.persist()` removal, `max_batch_size` → `get_max_batch_size()` |
| `cohere` | 3 | `cohere.Client()` → `cohere.ClientV2()`, `.check_api_key()` removal, `.generate(prompt=)` → `.chat()` |
| `mistralai` | 6 | Import path relocation to `mistralai.client.*`, `MistralClient` → `Mistral`, `.chat()` → `.chat.complete()`, `.chat_stream()` → `.chat.stream()`, `ChatMessage` removal |
| `haystack-ai` | 7 | `haystack.nodes` removal, `FARMReader` → `ExtractiveReader`, `BM25Retriever` → `InMemoryBM25Retriever`, `model_name_or_path` → `model`, `write_document` → `write_documents`, `Document.text` → `.content`, `add_node` → `add_component` |

**Total: 103 auto-fix rules across 13 AI SDKs.**

All provider-specific rules (OpenAI, Google, Vertex, LangChain) use exact class-name matching with `$` line anchors to prevent false positives on non-target providers (e.g., `ChatAnthropic` is never rewritten to `langchain_openai`). Multi-import lines that mix providers are safely skipped.

### Manual Migration Warnings

The registry also includes **30 manual migration warnings** for LangChain v0.2 deprecations plus **7 additional warnings** for LangChain v0.3+/v1.0 that cannot be auto-fixed because they require structural code changes. These appear in the `--breaking-changes` report with detailed migration notes:

- **Chain methods**: `.run()`, `.call()`, `.apply()`, `.arun()`, `.acall()` → `.invoke()` / `.batch()` / `.ainvoke()`
- **LLM/ChatModel methods**: `.predict()`, `.predict_messages()`, `.apredict()`, `.apredict_messages()`, `.call_as_llm()` → `.invoke()` / `.ainvoke()`
- **Deprecated chains**: `LLMChain`, `RetrievalQA`, `ConversationalRetrievalChain`, `FlareChain`, `create_extraction_chain`, `create_structured_output_chain`, `create_openai_fn_chain`
- **Deprecated agents**: `initialize_agent`, `AgentType`, `OpenAIFunctionsAgent`, `ZeroShotAgent`, `MRKLChain`, `ConversationalAgent`, `ConversationalChatAgent`, `ChatAgent`, `OpenAIMultiFunctionsAgent`, `StructuredChatAgent`, `XMLAgent`, `SelfAskWithSearchAgent`, `load_agent`, `LLMSingleActionAgent`
- **Other**: `VectorStoreIndexWrapper`, `NatBotChain.from_default`, `try_load_from_hub`, `CohereRerank`, tracer schema classes, `astream_events` V1, `@tool` decorator behavior change

## Example Output

```
──────────────── devcheck-ai Report ─────────────────
  11 dependencies checked  |  4 up to date  |  3 high risk  |  1 deprecated
─────────────────────────────────────────────────────

Status   Package         Ecosystem  Pinned      Latest      Released     Details
CRIT     old-lib         pypi       1.0.0       1.0.0       2020-01-01   DEPRECATED: No longer maintained
HIGH     openai           pypi       0.28.0      1.30.0      2024-05-15   Major version drift. Manual review required.
HIGH     langchain        npm        0.1.0       0.2.0       2024-06-01   Minor version drift. New features, possible deprecations.
LOW      requests         pypi       2.31.0      2.31.1      2024-05-20   Patch version drift. Bug fixes and security patches.
OK       fastapi          pypi       0.104.1     0.104.1     2024-05-01   Up to date
```

### With `--breaking-changes` flag

```
Known Breaking Changes:

  CRITICAL openai (pypi) 0.28.0 -> 3.1.0
    OpenAI Python SDK v1.0 replaced all module-level API calls with client-based APIs.
    openai.ChatCompletion.create -> client.chat.completions.create
      Use client.chat.completions.create(). Instantiate OpenAI() client first.
    openai.api_key = "..." -> OpenAI(api_key="...")
      API key passed to client constructor, not module-level.
    openai.embeddings_utils -> (removed)
      embeddings_utils.py removed. Use client.embeddings.create() + numpy.
    Official v1.0.0 Migration Guide: https://github.com/openai/openai-python/discussions/742
```

## Supported Manifests

| Ecosystem | Manifests |
|-----------|-----------|
| Python (PyPI) | `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` (PEP 621 + Poetry) |
| Node.js (npm) | `package.json` (`dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies`) |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No issues at or above the `--fail-on` threshold |
| 1 | Dependencies found at or above the risk threshold |
| 2 | Tool/runtime error |

## CI Integration

```yaml
# .github/workflows/depcheck.yml
name: Dependency Check
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install devcheck-ai
      - run: devcheck-ai ./ --format markdown -o depcheck-report.md
      - uses: actions/upload-artifact@v4
        with:
          name: dependency-report
          path: depcheck-report.md
```

## Smoke Testing

The `--smoke` flag creates an isolated virtual environment (Python) or temp directory (Node.js), installs each high-risk dependency, and attempts to import/require it. This catches:

- Packages that install but can't be imported (missing native deps, name mismatches)
- Import name differences (e.g., `pillow` imports as `PIL`, `python-dateutil` as `dateutil`)
- Broken installs from version pin conflicts

```bash
devcheck-ai ./my-project --smoke
```

## Registry integrity

The breaking-changes registry is fetched from a stable published URL and cached for
seven days, falling back to a bundled snapshot when offline. To pin it, set the expected
digest and any fetch that does not match is discarded:

```bash
export DEVCHECK_AI_REGISTRY_SHA256=$(curl -s \
  https://onthedrops.github.io/ai-sdk-breakage-registry/v1/registry.json.sha256 | cut -d' ' -f1)
```

The digest is served from the same origin as the data, so this is not a defence against a
compromised origin. It detects corrupted downloads and makes an unexpected change to the
published registry fail on your side rather than silently altering results.

## Why Not Dependabot/Snyk?

Those tools focus on **security vulnerabilities**. `devcheck-ai` focuses on **currentness and AI-code correctness** — is the version the AI assistant used actually the current one? Are there breaking changes between what was written and what's now live?

| Feature | devcheck-ai | Dependabot | Snyk |
|---------|-------------|------------|------|
| Version drift detection | Yes | Partial | Partial |
| Major version risk | Yes | No | No |
| AI SDK package mappings | Yes | No | No |
| Import smoke tests | Yes | No | No |
| Deprecation detection | Yes | Partial | Yes |
| Security CVEs | No | Yes | Yes |

## Contributing

Contributions welcome. Areas we'd like help with:

- **More package ecosystems** — Go modules, Rust crates, Ruby gems, Java Maven
- **AI SDK plugin rules** — Specific deprecation/breaking-change rules for OpenAI, Anthropic, LangChain, Vercel AI SDK, Google GenAI
- **Changelog parsing** — Automatically extract breaking changes from changelog text
- **More import name mappings** — The `_python_import_name` function could always use more entries

### Development

```bash
git clone https://github.com/onthedrops/devcheck-ai.git
cd devcheck-ai
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE).
