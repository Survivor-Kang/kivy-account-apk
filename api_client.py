"""
API 客户端：封装 getInfo / order/query / 登录 / 充值 四类接口。
"""
import re
import time
import json
from typing import Optional, Tuple, Dict, Any

import requests

from config import BASE_URL, HTTP_TIMEOUT, USER_AGENT


class ApiError(Exception):
    pass


# 解析 "14,464.297080" 这种带千分位的字符串为 float
def _parse_balance(s) -> float:
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return 0.0


class ApiClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    # ---------- 开放 API：token 鉴权 ----------

    def get_info(self, token_id: str, token_key: str) -> Dict[str, Any]:
        r = self.session.post(
            f"{BASE_URL}/api/user/getInfo",
            data={"tokenId": token_id, "tokenKey": token_key},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        j = r.json()
        if str(j.get("status")) != "1":
            raise ApiError(j.get("message", "getInfo 失败"))
        d = j.get("data") or {}
        return {
            "id": d.get("id"),
            "userName": d.get("userName", ""),
            "balance": _parse_balance(d.get("userBalance")),
        }

    def query_orders(self, token_id: str, token_key: str,
                     order_id: str, query_type: str = "0") -> list:
        """query_type: 0=单个 1=批量（批量时 order_id 用英文逗号分隔）"""
        r = self.session.post(
            f"{BASE_URL}/api/order/query",
            data={
                "tokenId": token_id,
                "tokenKey": token_key,
                "orderId": order_id,
                "type": query_type,
            },
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        j = r.json()
        if str(j.get("status")) != "1":
            raise ApiError(j.get("message", "订单查询失败"))
        data = j.get("data")
        if data is None:
            return []
        if isinstance(data, dict):
            return [data]
        return data

    # ---------- Web 会话：邮箱密码登录 ----------

    def web_login(self, email: str, password: str) -> requests.Response:
        """使用邮箱密码登录，会把 USERSID 写入 self.session.cookies。"""
        params = {"_t": str(int(time.time() * 1000))}
        r = self.session.post(
            f"{BASE_URL}/user/login/check.html",
            params=params,
            data={"user": email, "pass": password},
            headers={
                "Referer": f"{BASE_URL}/user/login",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        try:
            j = r.json()
        except ValueError:
            raise ApiError(f"登录返回非 JSON: {r.text[:200]}")
        return r

    def web_recharge_submit(self, rmb: float, pay_type: str = "alipay") -> Dict[str, Any]:
        """
        提交充值，返回解析后的 dict：
          { "ok": bool, "message": str, "pay_url": str, "raw": dict }
        pay_url 为完整支付页面 URL（由 data 字段里的路径拼接得到）。
        实际返回示例：
          {"status":1,"message":"订单创建成功","data":"/api/payHandler/pay?orderId=pay_xxx"}
        """
        r = self.session.post(
            f"{BASE_URL}/user/recharge/submit.html",
            data={"type": pay_type, "rmb": str(rmb)},
            headers={
                "Referer": f"{BASE_URL}/user",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        try:
            j = r.json()
        except ValueError:
            raise ApiError(f"充值提交返回非 JSON: {r.text[:200]}")

        pay_url = self._extract_pay_url(j)
        ok = str(j.get("status")) == "1"
        return {
            "ok": ok,
            "message": j.get("message", ""),
            "pay_url": pay_url,
            "raw": j,
        }

    @staticmethod
    def _extract_pay_url(j: Dict[str, Any]) -> str:
        """
        把 data 字段里的路径拼成完整 URL；若已经是完整 URL 则直接返回。
        同时兼容旧字段：url / qrUrl / payUrl 等。
        """
        if not isinstance(j, dict):
            return ""
        data = j.get("data")
        if isinstance(data, str) and data:
            if data.startswith("http://") or data.startswith("https://"):
                return data
            if data.startswith("/"):
                return f"{BASE_URL}{data}"
            m = re.search(r"https?://[^\s\"']+", data)
            if m:
                return m.group(0)
        for k in ("url", "qrUrl", "qr", "payUrl", "payurl"):
            v = j.get(k)
            if isinstance(v, str) and v:
                if v.startswith("http"):
                    return v
                if v.startswith("/"):
                    return f"{BASE_URL}{v}"
        return ""

    # ---------- Web 会话：订单分页列表（无需 tokenId，走登录 Cookie） ----------

    def web_get_orders(self, page: int = 1, row: int = 100, order_code: str = "") -> Dict[str, Any]:
        """
        调用 /user/order/getData.html 拉取当前登录账户的订单分页。
        返回：{"list": [...], "total": int, "raw": dict}
        兼容多种返回格式：
          - layui: {"code":0,"msg":"","count":N,"data":[...]}
          - 本站常见: {"status":1,"data":{"count":N,"list":[...]}}
          - 兜底:    {"status":1,"data":[...]}
        """
        r = self.session.post(
            f"{BASE_URL}/user/order/getData.html",
            data={
                "orderCode": str(order_code or ""),
                "page": str(page),
                "row": str(row),
            },
            headers={
                "Referer": f"{BASE_URL}/user",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        try:
            j = r.json()
        except ValueError:
            raise ApiError(f"订单列表返回非 JSON: {r.text[:200]}")

        # layui 格式
        if isinstance(j, dict) and "data" in j and "count" in j and "code" in j:
            data = j.get("data")
            return {
                "list": data if isinstance(data, list) else [],
                "total": int(j.get("count") or 0),
                "raw": j,
            }

        # 本站常见：data 是 dict，含 count/list
        data = j.get("data") if isinstance(j, dict) else None
        if isinstance(data, dict):
            lst = data.get("list") or data.get("data") or data.get("rows") or []
            total = data.get("count") or data.get("total") or data.get("totalCount") or 0
            return {
                "list": lst if isinstance(lst, list) else [],
                "total": int(total or 0),
                "raw": j,
            }

        # 兜底：data 直接是列表
        if isinstance(data, list):
            return {"list": data, "total": len(data), "raw": j}

        return {"list": [], "total": 0, "raw": j}

    # ---------- Web 会话：订单详情 / 卡密日志 ----------

    def web_get_order_detail(self, order_id: str) -> Dict[str, Any]:
        """
        调用 /user/order/queryOrderDetail.html，返回订单详情 dict（原样 JSON）。
        """
        r = self.session.post(
            f"{BASE_URL}/user/order/queryOrderDetail.html",
            data={"orderId": str(order_id)},
            headers={
                "Referer": f"{BASE_URL}/user",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            raise ApiError(f"订单详情返回非 JSON: {r.text[:200]}")

    def web_get_order_code_log(self, order_id: str, page: int = 1, row: int = 200) -> Dict[str, Any]:
        """
        调用 /user/order/getOrderCodeLog.html，返回卡密/发货日志分页：
          {"list": [...], "total": int, "raw": dict}
        """
        r = self.session.post(
            f"{BASE_URL}/user/order/getOrderCodeLog.html",
            data={
                "orderId": str(order_id),
                "page": str(page),
                "row": str(row),
            },
            headers={
                "Referer": f"{BASE_URL}/user",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        try:
            j = r.json()
        except ValueError:
            raise ApiError(f"卡密日志返回非 JSON: {r.text[:200]}")

        data = j.get("data") if isinstance(j, dict) else None
        # layui
        if isinstance(j, dict) and "count" in j and "data" in j:
            return {
                "list": j.get("data") if isinstance(j.get("data"), list) else [],
                "total": int(j.get("count") or 0),
                "raw": j,
            }
        if isinstance(data, dict):
            lst = data.get("list") or data.get("data") or data.get("rows") or []
            total = data.get("count") or data.get("total") or 0
            return {
                "list": lst if isinstance(lst, list) else [],
                "total": int(total or 0),
                "raw": j,
            }
        if isinstance(data, list):
            return {"list": data, "total": len(data), "raw": j}
        return {"list": [], "total": 0, "raw": j}

    # ---------- Token 管理：一键生成/读取 ----------

    def web_set_token(self) -> Dict[str, Any]:
        """
        POST /user/profile/setToken.html （空 body）
        触发后端生成/重置 tokenId + tokenKey。返回原始 JSON。
        """
        r = self.session.post(
            f"{BASE_URL}/user/profile/setToken.html",
            data={},
            headers={
                "Referer": f"{BASE_URL}/user",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            raise ApiError(f"setToken 返回非 JSON: {r.text[:200]}")

    def web_get_user_info(self) -> Dict[str, Any]:
        """
        POST /index/api/getuserInfo.html （空 body）
        返回当前登录用户的信息（含 tokenId/tokenKey）。
        """
        r = self.session.post(
            f"{BASE_URL}/index/api/getuserInfo.html",
            data={},
            headers={
                "Referer": f"{BASE_URL}/user",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            raise ApiError(f"getuserInfo 返回非 JSON: {r.text[:200]}")

    def refresh_token(self) -> Dict[str, str]:
        """
        一键刷新 token 的完整流程：
          1) web_login 已经在 session 里（由调用方保证）
          2) 调 setToken 生成新 token
          3) 调 getuserInfo 读回新的 tokenId/tokenKey
        返回 {"tokenId": "...", "tokenKey": "..."}；找不到字段时抛 ApiError。
        """
        self.web_set_token()
        info = self.web_get_user_info()
        data = info.get("data") if isinstance(info, dict) else None
        if not isinstance(data, dict):
            data = info if isinstance(info, dict) else {}

        token_id = (data.get("id") or data.get("tokenId") or data.get("token_id")
                    or data.get("appId") or data.get("app_id") or "")
        token_key = (data.get("userToken") or data.get("tokenKey") or data.get("token_key")
                    or data.get("appKey") or data.get("app_key") or "")

        if not token_id or not token_key:
            raise ApiError(f"未能从返回中解析到 tokenId/tokenKey：{info}")
        return {"tokenId": str(token_id), "tokenKey": str(token_key)}
