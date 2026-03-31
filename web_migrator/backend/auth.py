import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    expected_user = os.environ.get("AUTH_USER", "")
    expected_pass = os.environ.get("AUTH_PASSWORD", "")

    user_ok = secrets.compare_digest(
        credentials.username.encode(), expected_user.encode()
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode(), expected_pass.encode()
    )

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
