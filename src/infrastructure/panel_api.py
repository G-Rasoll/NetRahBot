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

    async def get_panel_stats(self) -> dict:
        async with httpx.AsyncClient(verify=False) as client:
            # ۱. لاگین و دریافت توکن جدید (دقیقاً مشابه کد requests)
            # توجه: اگر متغیرهای username و password در کلاس self نیستند،
            # باید آن‌ها را از فایل config ایمپورت کنی یا مستقیماً اینجا بنویسی.
            login_url = f"{self.base_url}/api/admin/token"
            login_response = await client.post(
                login_url,
                data={
                    "username": self.username,  # یوزرنیم پنل
                    "password": self.password  # پسورد پنل
                }
            )
            login_response.raise_for_status()  # اگر لاگین ارور بده همینجا مشخص میشه
            token_data = login_response.json()
            token = token_data["access_token"]

            headers = {"Authorization": f"Bearer {token}"}

            # ۲. دریافت اطلاعات ادمین
            admin_url = f"{self.base_url}/api/admin"
            admin_response = await client.get(admin_url, headers=headers)
            admin_response.raise_for_status()
            admin = admin_response.json()

            total_panel_traffic = admin.get("data_limit")
            used_panel_traffic = admin.get("used_traffic", 0)

            # ۳. دریافت لیست کاربران
            users_url = f"{self.base_url}/api/users"
            users_response = await client.get(users_url, headers=headers)
            users_response.raise_for_status()
            users_data = users_response.json()

            if isinstance(users_data, list):
                users = users_data
            elif isinstance(users_data, dict):
                users = users_data.get("users", [])
            else:
                users = []

            total_assigned = 0
            unlimited_users_count = 0

            # ۴. محاسبه ترافیک
            for user in users:
                data_limit = user.get("data_limit")
                if data_limit is None or data_limit == 0:
                    unlimited_users_count += 1
                    continue
                total_assigned += data_limit

            panel_remaining = max(total_panel_traffic - used_panel_traffic,
                                  0) if total_panel_traffic is not None else None
            assigned_percentage = (
                        (total_assigned / total_panel_traffic) * 100) if (
                        total_panel_traffic and total_panel_traffic > 0) else None

            return {
                "admin_username": admin.get("username"),
                "total_panel_traffic": total_panel_traffic,
                "used_panel_traffic": used_panel_traffic,
                "panel_remaining": panel_remaining,
                "users_count": len(users),
                "total_assigned": total_assigned,
                "assigned_percentage": assigned_percentage,
                "unlimited_users_count": unlimited_users_count
            }

panel_api = PanelApiService()
