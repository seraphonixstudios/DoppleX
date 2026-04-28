from __future__ import annotations

import os

PROVIDERS = {
    "X": {
        "name": "X",
        "authorize_url": os.environ.get(
            "YOU2_X_AUTH_URL",
            "https://twitter.com/i/oauth2/authorize",
        ),
        "token_url": os.environ.get(
            "YOU2_X_TOKEN_URL",
            "https://api.twitter.com/2/oauth2/token",
        ),
        "client_id": os.environ.get("YOU2_X_CLIENT_ID", ""),
        "redirect_port": int(os.environ.get("YOU2_X_REDIRECT_PORT", "53684")),
        "scopes": os.environ.get("YOU2_X_SCOPES", "tweet.write offline.access users.read"),
    },
    "TikTok": {
        "name": "TikTok",
        "authorize_url": os.environ.get(
            "YOU2_TIKTOK_AUTH_URL",
            "https://open-api.tiktok.com/platform/oauth/connect/authorize",
        ),
        "token_url": os.environ.get(
            "YOU2_TIKTOK_TOKEN_URL",
            "https://open-api.tiktok.com/oauth/access_token",
        ),
        "client_id": os.environ.get("YOU2_TIKTOK_CLIENT_ID", ""),
        "redirect_port": int(os.environ.get("YOU2_TIKTOK_REDIRECT_PORT", "53685")),
        "scopes": os.environ.get("YOU2_TIKTOK_SCOPES", "video.upload offline.access"),
    },
}
