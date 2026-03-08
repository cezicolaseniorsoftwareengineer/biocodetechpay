import sys
import os
from datetime import timedelta

# Add project root
sys.path.append(os.getcwd())

from app.core.config import settings
from app.auth.service import create_access_token

try:
    print("Testing JWT Creation...")
    token = create_access_token(
        data={"sub": "123"}, 
        expires_delta=timedelta(minutes=30)
    )
    print(f"Token: {token}")
    print("SUCCESS")
except Exception as e:
    print(f"FAILURE: {e}")
