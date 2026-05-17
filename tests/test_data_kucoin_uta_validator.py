import os
import pytest
from unittest.mock import patch, MagicMock
from src.data.kucoin_uta_validator import KuCoinUTAValidator


class TestKuCoinUTAValidator:
    @pytest.fixture
    def validator(self):
        with patch.dict(os.environ, {
            "KUCOIN_API_KEY": "test_key",
            "KUCOIN_API_SECRET": "test_secret",
            "KUCOIN_API_PASSPHRASE": "test_passphrase",
        }, clear=True):
            yield KuCoinUTAValidator()

    @pytest.fixture
    def unconfigured_validator(self):
        with patch.dict(os.environ, {}, clear=True):
            yield KuCoinUTAValidator()

    def test_is_configured_true(self, validator):
        assert validator.is_configured() is True

    def test_is_configured_false(self, unconfigured_validator):
        assert unconfigured_validator.is_configured() is False

    def test_generate_signature(self, validator):
        ts = "1700000000000"
        sig, enc_pass = validator._generate_signature(ts, "GET", "/api/v1/accounts")
        assert isinstance(sig, str)
        assert len(sig) > 0
        assert isinstance(enc_pass, str)
        assert len(enc_pass) > 0

    @patch("src.data.kucoin_uta_validator.requests.request")
    def test_make_request_success(self, mock_request, validator):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"currency": "USDT"}]}'
        mock_response.json.return_value = {"data": [{"currency": "USDT"}]}
        mock_request.return_value = mock_response
        result = validator._make_request("GET", "/api/v1/accounts")
        assert result["success"] is True
        assert result["status_code"] == 200

    @patch("src.data.kucoin_uta_validator.requests.request")
    def test_make_request_timeout(self, mock_request, validator):
        mock_request.side_effect = TimeoutError("timeout")
        result = validator._make_request("GET", "/api/v1/accounts")
        assert result["success"] is False
        assert result["status_code"] == 0

    @patch("src.data.kucoin_uta_validator.requests.request")
    def test_make_request_exception(self, mock_request, validator):
        mock_request.side_effect = Exception("network error")
        result = validator._make_request("GET", "/api/v1/accounts")
        assert result["success"] is False
        assert result["status_code"] == 0

    @patch("src.data.kucoin_uta_validator.requests.request")
    def test_validate_unified_account(self, mock_request, validator):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"currency": "USDT"}]}'
        mock_response.json.return_value = {"data": [{"currency": "USDT"}]}
        mock_request.return_value = mock_response
        result = validator.validate_unified_account()
        assert result["success"] is True
        assert result["account_count"] == 1

    @patch("src.data.kucoin_uta_validator.requests.request")
    def test_validate_ledgers(self, mock_request, validator):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"id": "1"}]}'
        mock_response.json.return_value = {"data": [{"id": "1"}]}
        mock_request.return_value = mock_response
        result = validator.validate_ledgers()
        assert result["success"] is True

    @patch("src.data.kucoin_uta_validator.requests.request")
    def test_validate_hf_accounts(self, mock_request, validator):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json.return_value = {"data": []}
        mock_request.return_value = mock_response
        result = validator.validate_hf_accounts()
        assert result["success"] is True

    @patch("src.data.kucoin_uta_validator.requests.request")
    def test_validate_hf_v3(self, mock_request, validator):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json.return_value = {"data": []}
        mock_request.return_value = mock_response
        result = validator.validate_hf_v3()
        assert result["success"] is True

    def test_run_validation_not_configured(self, unconfigured_validator):
        result = unconfigured_validator.run_validation()
        assert result["configured"] is False
        assert "SKIPPED" in result["summary"]

    @patch.object(KuCoinUTAValidator, "validate_unified_account")
    @patch.object(KuCoinUTAValidator, "validate_ledgers")
    @patch.object(KuCoinUTAValidator, "validate_hf_accounts")
    @patch.object(KuCoinUTAValidator, "validate_hf_v3")
    def test_run_validation_all_pass(self, mock_v3, mock_hf, mock_ledgers, mock_ua, validator):
        mock_ua.return_value = {"test": "UA", "endpoint": "/api/v1/accounts", "success": True, "status_code": 200}
        mock_ledgers.return_value = {"test": "Ledgers", "endpoint": "/api/v1/accounts/ledgers", "success": True, "status_code": 200}
        mock_hf.return_value = {"test": "HF", "endpoint": "/api/v1/accounts?type=trade-hf", "success": True, "status_code": 200}
        mock_v3.return_value = {"test": "V3", "endpoint": "/api/v3/hf/accounts", "success": True, "status_code": 200}
        result = validator.run_validation()
        assert result["configured"] is True
        assert result["summary"] == "READY"
        assert result["passed"] == 4

    @patch.object(KuCoinUTAValidator, "validate_unified_account")
    @patch.object(KuCoinUTAValidator, "validate_ledgers")
    @patch.object(KuCoinUTAValidator, "validate_hf_accounts")
    @patch.object(KuCoinUTAValidator, "validate_hf_v3")
    def test_run_validation_all_fail(self, mock_v3, mock_hf, mock_ledgers, mock_ua, validator):
        mock_ua.return_value = {"test": "UA", "endpoint": "/api/v1/accounts", "success": False, "status_code": 401, "error": "Unauthorized"}
        mock_ledgers.return_value = {"test": "Ledgers", "endpoint": "/api/v1/accounts/ledgers", "success": False, "status_code": 401, "error": "Unauthorized"}
        mock_hf.return_value = {"test": "HF", "endpoint": "/api/v1/accounts?type=trade-hf", "success": False, "status_code": 401, "error": "Unauthorized"}
        mock_v3.return_value = {"test": "V3", "endpoint": "/api/v3/hf/accounts", "success": False, "status_code": 401, "error": "Unauthorized"}
        result = validator.run_validation()
        assert result["configured"] is True
        assert result["summary"] == "FAILED"
        assert result["passed"] == 0
