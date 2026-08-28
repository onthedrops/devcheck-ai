"""Tests for the auto-fix engine."""

import shutil
import tempfile
from pathlib import Path

import pytest

from devcheck_ai.autofix import (
    FixEngine,
    FixPlan,
    FixReport,
    discover_python_files,
    FIX_RULES,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "old_sdk_code"


class TestFixRules:
    def test_rules_exist(self):
        assert len(FIX_RULES) > 0

    def test_all_rules_have_required_fields(self):
        for rule in FIX_RULES:
            assert "rule_id" in rule
            assert "package" in rule
            assert "pattern" in rule
            assert "replacement" in rule
            assert "confidence" in rule
            assert "migration_note" in rule

    def test_openai_rules_exist(self):
        openai_rules = [r for r in FIX_RULES if r["package"] == "openai"]
        assert len(openai_rules) >= 5

    def test_google_rules_exist(self):
        google_rules = [r for r in FIX_RULES if r["package"] == "google-generativeai"]
        assert len(google_rules) >= 8

    def test_vertex_rules_exist(self):
        vertex_rules = [r for r in FIX_RULES if r["package"] == "google-cloud-aiplatform"]
        assert len(vertex_rules) >= 10

    def test_transformers_rules_exist(self):
        tf_rules = [r for r in FIX_RULES if r["package"] == "transformers"]
        assert len(tf_rules) >= 3

    def test_langchain_rules_exist(self):
        lc_rules = [r for r in FIX_RULES if r["package"] == "langchain"]
        assert len(lc_rules) >= 20


class TestFileDiscovery:
    def test_finds_python_files(self):
        files = discover_python_files(FIXTURES_DIR)
        assert len(files) >= 5

    def test_excludes_pycache(self, tmp_path):
        # Create __pycache__ with a .py file
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "test.py").write_text("x = 1")
        # Create a real file
        (tmp_path / "real.py").write_text("x = 2")

        files = discover_python_files(tmp_path)
        assert len(files) == 1
        assert files[0].name == "real.py"

    def test_excludes_venv(self, tmp_path):
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "lib.py").write_text("x = 1")
        (tmp_path / "main.py").write_text("x = 2")

        files = discover_python_files(tmp_path)
        assert len(files) == 1
        assert files[0].name == "main.py"


class TestScanOpenAI:
    def test_finds_chat_completion_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "openai-py-chat-completion" in rule_ids

    def test_finds_completion_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "openai-py-completion" in rule_ids

    def test_finds_embedding_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "openai-py-embedding" in rule_ids

    def test_finds_image_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "openai-py-image" in rule_ids

    def test_finds_api_key_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "openai-py-api-key" in rule_ids

    def test_finds_error_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "openai-py-error-import" in rule_ids

    def test_all_openai_plans_have_high_or_medium_confidence(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        for plan in plans:
            assert plan.confidence in ("high", "medium")


class TestScanGoogle:
    def test_finds_import_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-import" in rule_ids

    def test_finds_configure_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-configure" in rule_ids

    def test_finds_generative_model_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-generative-model" in rule_ids

    def test_finds_caching_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-caching-import" in rule_ids

    def test_finds_types_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-types-import" in rule_ids

    def test_finds_generation_config_param(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-generation-config-param" in rule_ids

    def test_finds_generation_config_class(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-generation-config-class" in rule_ids

    def test_finds_model_generate_content(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-model-generate-content" in rule_ids

    def test_finds_model_generate_content_stream(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-model-generate-content-stream" in rule_ids

    def test_finds_model_start_chat(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "google-py-model-start-chat" in rule_ids

    def test_all_google_plans_have_valid_confidence(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        for plan in plans:
            assert plan.confidence in ("high", "medium", "low")


class TestScanVertex:
    def test_finds_import_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-import" in rule_ids

    def test_finds_init_pattern(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-init" in rule_ids

    def test_finds_generative_model_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-generative-model-extras-import" in rule_ids

    def test_finds_language_models_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-language-models-import" in rule_ids

    def test_finds_vision_models_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-vision-models-import" in rule_ids

    def test_finds_chat_model_from_pretrained(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-chat-model-from-pretrained" in rule_ids

    def test_finds_text_model_from_pretrained(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-text-model-from-pretrained" in rule_ids

    def test_finds_vision_model_from_pretrained(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-vision-model-from-pretrained" in rule_ids

    def test_finds_generative_model_create(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-generative-model-create" in rule_ids

    def test_finds_model_generate_content(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-model-generate-content" in rule_ids

    def test_finds_model_generate_content_stream(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-model-generate-content-stream" in rule_ids

    def test_finds_model_start_chat(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-model-start-chat" in rule_ids

    def test_finds_part_from_text(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-part-from-text" in rule_ids

    def test_finds_image_load(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-image-load" in rule_ids

    def test_finds_text_model_predict(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "vertex-py-text-model-predict" in rule_ids

    def test_all_vertex_plans_have_valid_confidence(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        for plan in plans:
            assert plan.confidence in ("high", "medium", "low")


class TestScanTransformers:
    def test_finds_use_auth_token(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="transformers")
        plans = engine.scan_file(FIXTURES_DIR / "transformers_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "transformers-py-use-auth-token" in rule_ids

    def test_finds_feature_extractor(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="transformers")
        plans = engine.scan_file(FIXTURES_DIR / "transformers_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "transformers-py-feature-extractor" in rule_ids

    def test_finds_lm_head(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="transformers")
        plans = engine.scan_file(FIXTURES_DIR / "transformers_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "transformers-py-lm-head" in rule_ids


class TestScanLangChain:
    def test_finds_schema_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-schema-messages" in rule_ids

    def test_finds_chat_models_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_old.py")

        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-chat-models" in rule_ids


class TestApplyFixes:
    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # Copy fixtures to temp dir so we can modify
        shutil.copytree(FIXTURES_DIR, self.tmpdir / "src")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dry_run_does_not_modify_files(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="openai")
        plans = engine.scan_all()
        original = (self.tmpdir / "src" / "openai_old.py").read_text()

        report = engine.apply_fixes(plans, dry_run=True)

        assert report.total_skipped > 0
        assert report.total_applied == 0
        # File should be unchanged
        assert (self.tmpdir / "src" / "openai_old.py").read_text() == original

    def test_write_fixes_modifies_openai_file(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="openai")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        assert report.total_applied > 0
        assert report.total_files_modified >= 1

        # Check that the file was modified
        content = (self.tmpdir / "src" / "openai_old.py").read_text()
        assert "client.chat.completions.create" in content
        assert "openai.ChatCompletion.create" not in content

    def test_backup_created_on_write(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="openai")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        assert report.backup_dir is not None
        assert report.backup_dir.exists()
        # Backup should contain original file
        backup_files = list(report.backup_dir.rglob("*.py"))
        assert len(backup_files) >= 1

    def test_transformers_fix_applied(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="transformers")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        assert report.total_applied > 0
        content = (self.tmpdir / "src" / "transformers_old.py").read_text()
        assert "AutoImageProcessor" in content
        assert "AutoFeatureExtractor" not in content
        assert "token=" in content
        assert "use_auth_token" not in content

    def test_langchain_fix_applied(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="langchain")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        assert report.total_applied > 0
        content = (self.tmpdir / "src" / "langchain_old.py").read_text()
        assert "langchain_core.messages" in content
        assert "langchain_openai" in content

    def test_google_fix_applied(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="google-generativeai")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        assert report.total_applied > 0
        content = (self.tmpdir / "src" / "google_old.py").read_text()
        assert "from google import genai" in content
        assert "import google.generativeai" not in content

    def test_vertex_fix_applied(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="google-cloud-aiplatform")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        assert report.total_applied > 0
        content = (self.tmpdir / "src" / "vertex_old.py").read_text()
        # Original active code should be commented out
        assert '# import vertexai' in content
        assert '# vertexai.init()' in content
        assert '# from vertexai.generative_models' in content
        assert '# from vertexai.language_models' in content
        assert '# from vertexai.vision_models' in content

    def test_vertex_client_injected(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="google-cloud-aiplatform")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        content = (self.tmpdir / "src" / "vertex_old.py").read_text()
        assert "genai.Client(vertexai=True" in content

    def test_google_no_syntax_errors(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="google-generativeai")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        # No syntax errors should be reported
        assert len(report.syntax_errors) == 0

    def test_vertex_no_syntax_errors(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="google-cloud-aiplatform")
        plans = engine.scan_all()

        report = engine.apply_fixes(plans, dry_run=False)

        assert len(report.syntax_errors) == 0

    def test_package_filter_limits_scope(self):
        engine_all = FixEngine(self.tmpdir / "src")
        plans_all = engine_all.scan_all()

        engine_openai = FixEngine(self.tmpdir / "src", package_filter="openai")
        plans_openai = engine_openai.scan_all()

        assert len(plans_all) > len(plans_openai)
        for p in plans_openai:
            assert p.package == "openai"


class TestGenerateDiff:
    def test_diff_shows_changes(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        diff = engine.generate_diff(plans)

        assert len(diff) > 0
        assert "client.chat.completions.create" in diff
        assert "openai.ChatCompletion.create" in diff

    def test_diff_format_is_unified(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="openai")
        plans = engine.scan_file(FIXTURES_DIR / "openai_old.py")

        diff = engine.generate_diff(plans)

        # Unified diff should have +/- markers
        assert "---" in diff
        assert "+++" in diff

    def test_diff_for_transformers(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="transformers")
        plans = engine.scan_file(FIXTURES_DIR / "transformers_old.py")

        diff = engine.generate_diff(plans)

        assert "AutoImageProcessor" in diff
        assert "token=" in diff

    def test_diff_for_google(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-generativeai")
        plans = engine.scan_file(FIXTURES_DIR / "google_old.py")

        diff = engine.generate_diff(plans)

        assert "from google import genai" in diff
        assert "import google.generativeai" in diff

    def test_diff_for_vertex(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        diff = engine.generate_diff(plans)

        assert len(diff) > 0
        assert "vertexai" in diff

    def test_diff_for_vertex_has_client_injection(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="google-cloud-aiplatform")
        plans = engine.scan_file(FIXTURES_DIR / "vertex_old.py")

        diff = engine.generate_diff(plans)

        assert "genai.Client(vertexai=True" in diff


class TestFixReport:
    def test_report_to_dict(self):
        report = FixReport(
            total_planned=5,
            total_applied=3,
            total_skipped=2,
            total_files_modified=1,
        )
        d = report.to_dict()
        assert d["total_planned"] == 5
        assert d["total_applied"] == 3
        assert d["total_skipped"] == 2
        assert d["total_files_modified"] == 1


class TestScanLangChainV02:
    def test_finds_schema_document_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-schema-document" in rule_ids

    def test_finds_text_splitter_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-text-splitter" in rule_ids

    def test_finds_vectorstores_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-vectorstores" in rule_ids

    def test_finds_document_loaders_import(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-document-loaders" in rule_ids

    def test_finds_community_chat_openai(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-community-chat-openai" in rule_ids

    def test_finds_community_embeddings_openai(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-community-embeddings-openai" in rule_ids

    def test_finds_community_llms_openai(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-community-llms-openai" in rule_ids

    def test_finds_fc_import_path(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-fc-import-path" in rule_ids

    def test_finds_convert_pydantic_function(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-convert-pydantic-function" in rule_ids

    def test_finds_convert_pydantic_tool(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-convert-pydantic-tool" in rule_ids

    def test_finds_convert_python_function(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-convert-python-function" in rule_ids

    def test_finds_format_tool_function(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-format-tool-function" in rule_ids

    def test_finds_format_tool_tool(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-format-tool-tool" in rule_ids

    def test_finds_get_relevant_docs(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-get-relevant-docs" in rule_ids

    def test_finds_aget_relevant_docs(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-aget-relevant-docs" in rule_ids

    def test_finds_chat_openai_no_model(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-chat-openai-no-model" in rule_ids


class TestLangChainV02FalsePositives:
    """Ensure non-OpenAI community imports are NOT rewritten."""

    def test_no_false_positive_chat_anthropic(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("from langchain_community.chat_models import ChatAnthropic\n")
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-community-chat-openai" not in rule_ids

    def test_no_false_positive_huggingface_embeddings(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("from langchain_community.embeddings import HuggingFaceEmbeddings\n")
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-community-embeddings-openai" not in rule_ids

    def test_no_false_positive_anthropic_llm(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("from langchain_community.llms import Anthropic\n")
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-community-llms-openai" not in rule_ids

    def test_no_false_positive_chat_openai_with_args(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text('llm = ChatOpenAI(model="gpt-4", temperature=0.7)\n')
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-chat-openai-no-model" not in rule_ids

    def test_no_false_positive_multi_import_community(self, tmp_path):
        """Multi-import line with ChatOpenAI + other classes should not be rewritten."""
        f = tmp_path / "test.py"
        f.write_text("from langchain_community.chat_models import ChatOpenAI, ChatAnthropic\n")
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-community-chat-openai" not in rule_ids

    # ── False positive guards for original broad rules (now tightened) ──

    def test_no_false_positive_langchain_chat_anthropic(self, tmp_path):
        """ChatAnthropic from langchain.chat_models should NOT be rewritten to langchain_openai."""
        f = tmp_path / "test.py"
        f.write_text("from langchain.chat_models import ChatAnthropic\n")
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-chat-models" not in rule_ids

    def test_no_false_positive_langchain_huggingface_embeddings(self, tmp_path):
        """HuggingFaceEmbeddings from langchain.embeddings should NOT be rewritten to langchain_openai."""
        f = tmp_path / "test.py"
        f.write_text("from langchain.embeddings import HuggingFaceEmbeddings\n")
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-embeddings" not in rule_ids

    def test_no_false_positive_langchain_anthropic_llm(self, tmp_path):
        """Anthropic from langchain.llms should NOT be rewritten to langchain_openai."""
        f = tmp_path / "test.py"
        f.write_text("from langchain.llms import Anthropic\n")
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-llms" not in rule_ids

    def test_no_false_positive_langchain_multi_import_chat_models(self, tmp_path):
        """Multi-import with ChatOpenAI + other should NOT be rewritten."""
        f = tmp_path / "test.py"
        f.write_text("from langchain.chat_models import ChatOpenAI, ChatAnthropic\n")
        engine = FixEngine(tmp_path, package_filter="langchain")
        plans = engine.scan_file(f)
        rule_ids = [p.rule_id for p in plans]
        assert "langchain-py-chat-models" not in rule_ids


class TestLangChainV02ApplyFixes:
    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        shutil.copytree(FIXTURES_DIR, self.tmpdir / "src")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_v02_fix_applied(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="langchain")
        plans = engine.scan_all()
        report = engine.apply_fixes(plans, dry_run=False)
        assert report.total_applied > 0
        content = (self.tmpdir / "src" / "langchain_v02_old.py").read_text()
        # Import path changes
        assert "from langchain_core.documents import Document" in content
        assert "from langchain_text_splitters import" in content
        assert "from langchain_community.vectorstores import" in content
        assert "from langchain_community.document_loaders import" in content
        # Community → provider
        assert "from langchain_openai import ChatOpenAI as CommunityChatOpenAI" in content
        assert "from langchain_openai import OpenAIEmbeddings as CommunityOpenAIEmbeddings" in content
        assert "from langchain_openai import OpenAI as CommunityOpenAILLM" in content
        # Function calling
        assert "from langchain_core.utils.function_calling import" in content
        assert "convert_to_openai_function" in content
        assert "convert_to_openai_tool" in content
        assert "convert_pydantic_to_openai_function" not in content
        assert "format_tool_to_openai_function" not in content
        # Retriever methods
        assert ".invoke(" in content
        assert ".ainvoke(" in content
        assert ".get_relevant_documents(" not in content
        assert ".aget_relevant_documents(" not in content
        # ChatOpenAI no model
        assert 'ChatOpenAI(model="gpt-4")' in content

    def test_v02_no_syntax_errors(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="langchain")
        plans = engine.scan_all()
        report = engine.apply_fixes(plans, dry_run=False)
        assert len(report.syntax_errors) == 0

    def test_v02_false_positives_preserved(self):
        engine = FixEngine(self.tmpdir / "src", package_filter="langchain")
        plans = engine.scan_all()
        report = engine.apply_fixes(plans, dry_run=False)
        content = (self.tmpdir / "src" / "langchain_v02_old.py").read_text()
        # Non-OpenAI imports should remain unchanged
        assert "from langchain_community.chat_models import ChatAnthropic" in content
        assert "from langchain_community.embeddings import HuggingFaceEmbeddings" in content
        assert "from langchain_community.llms import Anthropic" in content

    def test_v02_idempotent(self):
        """Re-scanning after applying fixes should find zero patterns."""
        engine = FixEngine(self.tmpdir / "src", package_filter="langchain")
        plans = engine.scan_all()
        engine.apply_fixes(plans, dry_run=False)
        # Re-scan
        plans2 = engine.scan_all()
        assert len(plans2) == 0

    def test_v02_diff_shows_changes(self):
        engine = FixEngine(FIXTURES_DIR, package_filter="langchain")
        plans = engine.scan_file(FIXTURES_DIR / "langchain_v02_old.py")
        diff = engine.generate_diff(plans)
        assert len(diff) > 0
        assert "langchain_core.documents" in diff
        assert "langchain_text_splitters" in diff
        assert "convert_to_openai_function" in diff
        assert ".invoke(" in diff
