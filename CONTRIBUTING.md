# Contributing to devcheck-ai

Thank you for your interest in improving devcheck-ai. This tool helps developers catch deprecated AI SDK patterns and automatically fix them.

## Ways to Contribute

### 1. Add auto-fix rules

Auto-fix rules live in `src/devcheck_ai/autofix.py` in the `FIX_RULES` list. Each rule is a dictionary:

```python
{
    "rule_id": "package-py-rule-name",
    "package": "package-name",
    "pattern": r"old\.pattern\(",       # regex matching deprecated code
    "replacement": "new.pattern(",       # replacement text
    "confidence": "high",               # high | medium | low
    "needs_client": False,              # True if fix requires network/API
    "migration_note": "What changed and why",
}
```

**Guidelines:**
- Only add rules for **safe one-line transformations** — if the fix requires restructuring code, add it to the registry as a warning instead
- Use `confidence: high` only when the pattern unambiguously identifies the deprecated API
- Use `$` line anchors for provider-specific patterns to avoid false positives across providers
- Test your rule against the test file in `tests/test_autofix.py`

### 2. Improve detection

Found a deprecated pattern that devcheck-ai doesn't catch? The breaking changes data comes from the [ai-sdk-breakage-registry](https://github.com/onthedrops/ai-sdk-breakage-registry). Add the entry there first, then add a corresponding auto-fix rule here if the transformation is safe.

### 3. Report bugs

Open an issue with:
- The deprecated code you expected to be caught
- What devcheck-ai reported (or didn't)
- The SDK package and version

### 4. Support a new ecosystem

Currently supports Python (PyPI) and JavaScript (npm). To add a new ecosystem:
1. Add a manifest parser in `src/devcheck_ai/manifests.py`
2. Add registry version-check logic in `src/devcheck_ai/registries.py`
3. Add tests in `tests/test_manifests.py` and `tests/test_registries.py`

## Development Setup

```bash
git clone https://github.com/onthedrops/devcheck-ai.git
cd devcheck-ai
pip install -e ".[dev]"
pytest tests/
```

## Testing

```bash
# Run all tests
pytest tests/

# Test on a real project
devcheck-ai scan /path/to/your/project

# Dry-run fixes
devcheck-ai scan /path/to/your/project --fix

# Apply fixes (creates backups)
devcheck-ai scan /path/to/your/project --write-fixes
```

## Code of Conduct

Be respectful. Be constructive. Don't add auto-fix rules that could break working code — when in doubt, mark `confidence: low` and let the user decide.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
