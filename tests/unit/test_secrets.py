import pytest
from unittest.mock import MagicMock, patch
from src.utils.secrets import get_user_credential

@patch("google.cloud.secretmanager.SecretManagerServiceClient")
@patch("os.getenv")
def test_get_user_credential_success(mock_getenv, mock_client_class):
    mock_getenv.side_effect = lambda x: "test-project" if x in ["GOOGLE_CLOUD_PROJECT", "PROJECT_ID"] else None
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.payload.data.decode.return_value = "fake-secret"
    mock_client.access_secret_version.return_value = mock_response
    
    val = get_user_credential("user123", "jira")
    assert val == "fake-secret"
    
    expected_name = "projects/test-project/secrets/user-credentials--user123--jira/versions/latest"
    mock_client.access_secret_version.assert_called_once_with(request={"name": expected_name})

@patch("google.cloud.secretmanager.SecretManagerServiceClient")
@patch("os.getenv")
def test_get_user_credential_failure(mock_getenv, mock_client_class):
    mock_getenv.side_effect = lambda x: "test-project" if x in ["GOOGLE_CLOUD_PROJECT", "PROJECT_ID"] else None
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.access_secret_version.side_effect = Exception("Not found")
    
    val = get_user_credential("user123", "jira")
    assert val is None
