#!/usr/bin/env python3
"""
Tests for AI Filter Engine (Phase 5)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.ai_filter import (
    AIConfig,
    AIError,
    AIFilterEngine,
    CopilotContext,
    FilterBuildRequest,
    OllamaClient,
    SelectionContext,
)


class TestAIConfig:
    """Tests for AIConfig."""

    def test_default_config(self):
        cfg = AIConfig()
        assert cfg.enabled is False
        assert cfg.ollama_url == "http://localhost:11434"
        assert cfg.model == "qwen2.5-coder:7b"
        assert cfg.timeout_seconds == 30.0
        assert cfg.max_tokens == 2048
        assert cfg.temperature == 0.1
        assert cfg.selection_assist is True
        assert cfg.nl_filter_builder is True
        assert cfg.copilot is True
        assert cfg.trust_level == 0

    def test_custom_config(self):
        cfg = AIConfig(
            enabled=True,
            ollama_url="http://custom:11434",
            model="llama3:8b",
            timeout_seconds=60.0,
            temperature=0.5,
        )
        assert cfg.enabled is True
        assert cfg.ollama_url == "http://custom:11434"
        assert cfg.model == "llama3:8b"
        assert cfg.timeout_seconds == 60.0
        assert cfg.temperature == 0.5


class TestSelectionContext:
    """Tests for SelectionContext."""

    def test_to_prompt(self):
        ctx = SelectionContext(
            group_hash="abc123def456",
            file_size=1024,
            files=[
                {
                    "name": "file1.txt",
                    "path": "/data/file1.txt",
                    "mtime": "2024-01-01",
                    "is_ref": False,
                    "depth": 2,
                    "hygiene_score": 0.9
                },
                {
                    "name": "file2.txt",
                    "path": "/ref/file2.txt",
                    "mtime": "2024-01-02",
                    "is_ref": True,
                    "depth": 1,
                    "hygiene_score": 1.0
                }
            ]
        )

        prompt = ctx.to_prompt()

        assert "abc123def456" in prompt
        assert "1024" in prompt
        assert "file1.txt" in prompt
        assert "file2.txt" in prompt
        assert "[REF]" in prompt
        assert "Entscheide:" in prompt


class TestFilterBuildRequest:
    """Tests for FilterBuildRequest."""

    def test_to_prompt(self):
        req = FilterBuildRequest(
            user_text="Delete copies with (1) in name",
            available_filters=["path_priority", "artifact", "filename_hygiene"],
            context={"reference_paths": ["/ref"]}
        )

        prompt = req.to_prompt()

        assert 'Delete copies with (1) in name' in prompt
        assert "path_priority" in prompt
        assert "artifact" in prompt
        assert "filename_hygiene" in prompt
        assert "JSON-Pipeline" in prompt


class TestCopilotContext:
    """Tests for CopilotContext."""

    def test_creation(self):
        ctx = CopilotContext(
            current_mode="select",
            trust_level=2,
            active_filters=["path_priority", "artifact"],
            recent_errors=[],
            quarantine_usage_gb=5.5,
            quarantine_limit_gb=100.0
        )
        assert ctx.current_mode == "select"
        assert ctx.trust_level == 2
        assert len(ctx.active_filters) == 2


class TestOllamaClient:
    """Tests for OllamaClient."""

    @pytest.fixture
    def config(self):
        return AIConfig(
            ollama_url="http://test:11434",
            model="test-model",
            timeout_seconds=10.0
        )

    @pytest.fixture
    def client(self, config):
        return OllamaClient(config)

    @pytest.fixture
    def mock_resp(self):
        """Create a properly mocked async context manager response."""
        mock_r = AsyncMock()
        mock_r.status = 200
        mock_r.json = AsyncMock(return_value={"response": "Test response"})
        mock_r.content = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        return mock_r

    @pytest.fixture
    def mock_session(self, mock_resp):
        """Create a mocked session."""
        mock_sess = MagicMock()
        # session.post should return an async context manager (not a coroutine)
        mock_sess.post = MagicMock(return_value=mock_resp)
        mock_sess.close = AsyncMock()
        return mock_sess

    @pytest.mark.asyncio
    async def test_context_manager_creates_session(self, client):
        async with client as c:
            assert c.session is not None
        # Session should be closed after exit

    @pytest.mark.asyncio
    async def test_generate_uses_session(self, client, mock_session, mock_resp):
        mock_resp.json.return_value = {"response": "Test response"}
        client.session = mock_session

        result = await client.generate("Test prompt", system="System prompt")

        assert result == "Test response"
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "/api/generate" in call_args[0][0]
        assert call_args[1]["json"]["prompt"] == "Test prompt"
        assert call_args[1]["json"]["system"] == "System prompt"

    @pytest.mark.asyncio
    async def test_generate_error_status(self, client, mock_session, mock_resp):
        mock_resp.status = 500
        client.session = mock_session

        with pytest.raises(AIError):
            await client.generate("Test prompt")

    @pytest.mark.asyncio
    async def test_chat_completion(self, client, mock_session, mock_resp):
        mock_resp.json.return_value = {"message": {"content": "Chat response"}}
        client.session = mock_session

        result = await client.chat([{"role": "user", "content": "Hello"}])

        assert result == "Chat response"
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "/api/chat" in call_args[0][0]


class TestAIFilterEngine:
    """Tests for AIFilterEngine."""

    @pytest.fixture
    def config(self):
        return AIConfig(enabled=True)

    @pytest.fixture
    def engine(self, config):
        return AIFilterEngine(config)

    @pytest.mark.asyncio
    async def test_initialize_success(self, engine):
        with patch.object(OllamaClient, 'generate', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = "OK"

            result = await engine.initialize()

            assert result is True
            assert engine._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_failure(self, engine):
        with patch.object(OllamaClient, 'generate', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = Exception("Connection refused")

            result = await engine.initialize()

            assert result is False
            assert engine._initialized is False

    @pytest.mark.asyncio
    async def test_selection_assist_disabled(self, engine):
        engine.config.selection_assist = False
        engine._initialized = True

        ctx = SelectionContext(group_hash="hash", file_size=100, files=[{"name": "f1"}, {"name": "f2"}])

        result = await engine.selection_assist(ctx)

        assert result is None

    @pytest.mark.asyncio
    async def test_selection_assist_not_initialized(self, engine):
        engine.config.selection_assist = True
        engine._initialized = False

        ctx = SelectionContext(group_hash="hash", file_size=100, files=[{"name": "f1"}, {"name": "f2"}])

        result = await engine.selection_assist(ctx)

        assert result is None

    @pytest.mark.asyncio
    async def test_selection_assist_parses_number(self, engine):
        engine.config.selection_assist = True
        engine._initialized = True

        with patch.object(engine, 'client') as mock_client:
            mock_client.generate = AsyncMock(return_value="2\n(Reason: newer file)")

            ctx = SelectionContext(
                group_hash="hash",
                file_size=100,
                files=[
                    {"name": "old.txt", "path": "/a/old.txt", "is_ref": False},
                    {"name": "new.txt", "path": "/b/new.txt", "is_ref": False},
                    {"name": "ref.txt", "path": "/ref/ref.txt", "is_ref": True}
                ]
            )

            result = await engine.selection_assist(ctx)

            assert result == 1  # 0-based index for "2"

    @pytest.mark.asyncio
    async def test_selection_assist_out_of_bounds(self, engine):
        engine.config.selection_assist = True
        engine._initialized = True

        with patch.object(engine, 'client') as mock_client:
            mock_client.generate = AsyncMock(return_value="5")  # Only 2 files

            ctx = SelectionContext(group_hash="hash", file_size=100, files=[{"name": "f1"}, {"name": "f2"}])

            result = await engine.selection_assist(ctx)

            assert result is None

    @pytest.mark.asyncio
    async def test_selection_assist_exception_handled(self, engine):
        engine.config.selection_assist = True
        engine._initialized = True

        with patch.object(engine, 'client') as mock_client:
            mock_client.generate = AsyncMock(side_effect=Exception("LLM error"))

            ctx = SelectionContext(group_hash="hash", file_size=100, files=[{"name": "f1"}])

            result = await engine.selection_assist(ctx)

            assert result is None

    @pytest.mark.asyncio
    async def test_build_filter_pipeline_disabled(self, engine):
        engine.config.nl_filter_builder = False
        engine._initialized = True

        req = FilterBuildRequest("test", ["filter1"])

        result = await engine.build_filter_pipeline(req)

        assert result is None

    @pytest.mark.asyncio
    async def test_build_filter_pipeline_parses_json(self, engine):
        engine.config.nl_filter_builder = True
        engine._initialized = True

        with patch.object(engine, 'client') as mock_client:
            mock_client.generate = AsyncMock(return_value='{"pipeline": [{"type": "artifact", "params": {}}]}')

            req = FilterBuildRequest("Delete artifacts", ["artifact"])

            result = await engine.build_filter_pipeline(req)

            assert result is not None
            assert "pipeline" in result
            assert result["pipeline"][0]["type"] == "artifact"

    @pytest.mark.asyncio
    async def test_build_filter_pipeline_invalid_json(self, engine):
        engine.config.nl_filter_builder = True
        engine._initialized = True

        with patch.object(engine, 'client') as mock_client:
            mock_client.generate = AsyncMock(return_value="This is not JSON")

            req = FilterBuildRequest("test", ["filter1"])

            result = await engine.build_filter_pipeline(req)

            assert result is None

    @pytest.mark.asyncio
    async def test_copilot_query_disabled(self, engine):
        engine.config.copilot = False
        engine._initialized = True

        ctx = CopilotContext("select", 0, [], [], 0, 100)

        result = await engine.copilot_query(ctx, "How to delete?")

        assert "nicht verfügbar" in result

    @pytest.mark.asyncio
    async def test_copilot_query_not_initialized(self, engine):
        engine.config.copilot = True
        engine._initialized = False

        ctx = CopilotContext("select", 0, [], [], 0, 100)

        result = await engine.copilot_query(ctx, "How to delete?")

        assert "nicht verfügbar" in result

    @pytest.mark.asyncio
    async def test_copilot_query_works(self, engine):
        engine.config.copilot = True
        engine._initialized = True

        with patch.object(engine, 'client') as mock_client:
            mock_client.chat = AsyncMock(return_value="You can use F8 to delete.")

            ctx = CopilotContext(
                current_mode="select",
                trust_level=0,
                active_filters=["artifact"],
                recent_errors=[],
                quarantine_usage_gb=10,
                quarantine_limit_gb=100
            )

            result = await engine.copilot_query(ctx, "How to delete?")

            assert result == "You can use F8 to delete."

    def test_build_copilot_system_prompt(self, engine):
        ctx = CopilotContext(
            current_mode="execute",
            trust_level=2,
            active_filters=["path_priority", "artifact"],
            recent_errors=[{"error": "Permission denied"}],
            quarantine_usage_gb=25.5,
            quarantine_limit_gb=100.0,
            last_operation="safe_move: 50 files",
            selected_files=["/a.txt", "/b.txt"]
        )

        prompt = engine._build_copilot_system_prompt(ctx)

        assert "Copilot" in prompt
        assert "execute" in prompt
        assert "ASSISTED" in prompt  # Level 2
        assert "path_priority, artifact" in prompt
        assert "25.5/100.0 GB" in prompt
        assert "safe_move: 50 files" in prompt
        assert "2" in prompt  # selected files count


class TestAIError:
    """Tests for AIError exception."""

    def test_ai_error(self):
        err = AIError("Test error")
        assert str(err) == "Test error"
        assert isinstance(err, Exception)
