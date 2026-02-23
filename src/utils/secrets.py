import os
import logging
from typing import Optional
from google.cloud import secretmanager

logger = logging.getLogger(__name__)

def get_user_credential(user_id: str, service_name: str) -> Optional[str]:
    """
    Fetch a user-specific credential for a service from Google Cloud Secret Manager.
    Path: projects/{project}/secrets/user-credentials/{user_id}/{service_name}
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT or PROJECT_ID not set")
        return None

    # The secret name is structured as user-credentials--{user_id}--{service_name}
    secret_id = f"user-credentials--{user_id}--{service_name}"
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.warning(f"Failed to fetch secret {secret_id}: {e}")
        return None
