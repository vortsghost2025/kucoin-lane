import pytest
from unittest.mock import patch, MagicMock
from src.execution.exchange_client import (
    is_transient_error,
    retry_on_error,
    ExchangeClientFactory,
)


class TestExchangeClient:
    def test_is_transient_error_rate_limit(self):
        assert is_transient_error(Exception("rate limit exceeded")) is True
        assert is_transient_error(Exception("Rate Limit")) is True

    def test_is_transient_error_timeout(self):
        assert is_transient_error(TimeoutError("timed out")) is True

    def test_is_transient_error_connection(self):
        assert is_transient_error(ConnectionError("connection refused")) is True

    def test_is_transient_error_non_transient(self):
        assert is_transient_error(ValueError("bad value")) is False
        assert is_transient_error(Exception("critical error")) is False

    def test_is_transient_error_http_5xx(self):
        assert is_transient_error(Exception("HTTP 500")) is True
        assert is_transient_error(Exception("Internal Server Error")) is True
        assert is_transient_error(Exception("Bad Gateway")) is True
        assert is_transient_error(Exception("Service Unavailable")) is True
        assert is_transient_error(Exception("Gateway Timeout")) is True

    def test_retry_on_error_success_first_attempt(self):
        def mock_fn():
            return "success"
        decorated = retry_on_error(max_retries=3)(mock_fn)
        result = decorated()
        assert result == "success"

    def test_retry_on_error_transient_failure(self):
        call_log = []
        def mock_fn():
            call_log.append(1)
            if len(call_log) == 1:
                raise Exception("rate limit")
            return "success"
        decorated = retry_on_error(max_retries=3, base_delay=0.01)(mock_fn)
        result = decorated()
        assert result == "success"
        assert len(call_log) == 2

    def test_retry_on_error_non_transient_raises(self):
        def mock_fn():
            raise ValueError("bad input")
        decorated = retry_on_error(max_retries=3, base_delay=0.01)(mock_fn)
        with pytest.raises(ValueError):
            decorated()

    def test_retry_on_error_all_fail(self):
        call_log = []
        def mock_fn():
            call_log.append(1)
            raise Exception("rate limit")
        decorated = retry_on_error(max_retries=2, base_delay=0.01)(mock_fn)
        with pytest.raises(Exception, match="rate limit"):
            decorated()
        assert len(call_log) == 3

    def test_retry_on_error_transient_only_false(self):
        call_log = []
        def mock_fn():
            call_log.append(1)
            if len(call_log) == 1:
                raise ValueError("bad input")
            return "success"
        decorated = retry_on_error(max_retries=3, base_delay=0.01, transient_only=False)(mock_fn)
        result = decorated()
        assert result == "success"
        assert len(call_log) == 2

    def test_retry_on_error_on_retry_callback(self):
        callback = MagicMock()
        call_log = []
        def mock_fn():
            call_log.append(1)
            if len(call_log) == 1:
                raise Exception("timeout")
            return "success"
        decorated = retry_on_error(max_retries=3, base_delay=0.01, on_retry=callback)(mock_fn)
        decorated()
        callback.assert_called_once()

    def test_exchange_client_factory_reset_cache(self):
        ExchangeClientFactory._adapter_cache = "cached"
        ExchangeClientFactory.reset_cache()
        assert ExchangeClientFactory._adapter_cache is None

    @patch("src.execution.exchange_client.ExchangeClientFactory._wrap_with_retry")
    @patch("src.execution.exchange_adapter.create_exchange_adapter")
    def test_get_exchange_adapter(self, mock_create, mock_wrap):
        mock_adapter = MagicMock()
        mock_create.return_value = mock_adapter
        ExchangeClientFactory.reset_cache()
        result = ExchangeClientFactory.get_exchange_adapter()
        assert result == mock_adapter

    @patch("src.execution.exchange_adapter.create_exchange_adapter")
    def test_get_exchange_adapter_cached(self, mock_create):
        mock_adapter = MagicMock()
        ExchangeClientFactory._adapter_cache = mock_adapter
        result = ExchangeClientFactory.get_exchange_adapter()
        assert result == mock_adapter
        mock_create.assert_not_called()
