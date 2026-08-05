# File: src/infrastructure/panel_api.py
import os
import json
import secrets
import string
import httpx
import logging
from config import PANEL_BASE_URL, PANEL_ADMIN_USERNAME, PANEL_ADMIN_PASSWORD, \
    TOKEN_CACHE_FILE

logger = logging.getLogger(__name__)


class PanelApiService:
    def __init__(self):
        self.base_url = PANEL_BASE_URL
        self.username = PANEL_ADMIN_USERNAME
        self.password = PANEL_ADMIN_PASSWORD
        self.token_file = TOKEN_CACHE_FILE

    async def get_access_token(self) -> str:
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    cache = json.load(f)
                    return cache.get("access_token")
            except Exception:
                pass

        login_url = f"{self.base_url}/api/admin/token"
        payload = {"username": self.username, "password": self.password}

        async with httpx.AsyncClient(
                verify=False) as client:  # verify=False اگر SSL پنل ولید نیست
            response = await client.post(login_url, data=payload)
            if response.status_code in [200, 201]:
                token_data = response.json()
                with open(self.token_file, "w") as f:
                    json.dump(token_data, f)
                return token_data.get("access_token")
            else:
                raise Exception(
                    f"Panel Login Error: {response.status_code} - {response.text}")

    def generate_random_username(self, sub_type, telegram_id,
                                 brand_name="NetRah", custom_name=None) -> str:
        allowed_chars = string.ascii_lowercase + string.digits
        random_suffix = ''.join(secrets.choice(allowed_chars) for _ in range(6))

        if sub_type == "Manual":
            name_part = custom_name if custom_name else "Rnd"
            # الگوی درخواستی: Brand_Manual_AdminUserId_Name_wypfno
            return f"{brand_name}_Manual_{telegram_id}_{name_part}_{random_suffix}"

        return f"{brand_name}_{sub_type}_{telegram_id}_{random_suffix}"

    async def create_user_config(self, sub_type, telegram_id, limit_gb: float,
                                 brand_name="NetRah", custom_name=None) -> str:
        token = await self.get_access_token()
        user_url = f"{self.base_url}/api/user"
        headers = {"Authorization": f"Bearer {token}"}

        data_limit_bytes = int(limit_gb * (1024 ** 3))
        username = self.generate_random_username(
            sub_type=sub_type, telegram_id=telegram_id,
            brand_name=brand_name, custom_name=custom_name
        )

        payload = {
            "username": username,
            "proxies": {"vless": {}, "vmess": {}, "trojan": {},
                        "shadowsocks": {}},
            "inbounds": {},
            "group_ids": [1],
            "expire": 0,
            "data_limit": data_limit_bytes,
            "data_limit_reset_strategy": "no_reset"
        }

        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(user_url, json=payload,
                                         headers=headers)

            if response.status_code == 401:
                if os.path.exists(self.token_file):
                    os.remove(self.token_file)
                token = await self.get_access_token()
                headers["Authorization"] = f"Bearer {token}"
                response = await client.post(user_url, json=payload,
                                             headers=headers)

            if response.status_code in [200, 201]:
                user_data = response.json()
                logger.info(
                    f"Auto-generated config for [{username}] successfully.")
                return user_data.get("subscription_url")
            else:
                raise Exception(
                    f"Config Creation Error: {response.status_code} - {response.text}")

panel_api = PanelApiService()
