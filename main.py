"""
多账户管理工具 - 移动端版（Kivy）
所有中文文本使用内置中文字体，避免方框乱码。
"""
import os
import sys
import threading
import webbrowser

from kivy.app import App
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.clock import Clock

import db
import crypto
from api_client import ApiClient, ApiError

# ---------- 中文字体注册（关键，否则中文全是方框） ----------
def _register_chinese_font():
    candidates = [
        os.path.join(os.path.dirname(__file__), "NotoSansSC-Regular.otf"),
        os.path.join(os.path.dirname(__file__), "NotoSansSC-Regular.ttf"),
        os.path.join(os.path.dirname(__file__), "SourceHanSansSC.otf"),
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/DroidSansFallback.ttf",
        "/system/fonts/NotoSansSC-Regular.otf",
    ]
    font_path = None
    for p in candidates:
        if os.path.exists(p):
            font_path = p
            break
    if font_path:
        LabelBase.register("CN", font_path)
        LabelBase.register("CN-Bold", font_path)
    else:
        # 没找到中文字体就用默认（在 Android 上一般 /system/fonts 下有）
        LabelBase.register("CN", "Roboto")
        LabelBase.register("CN-Bold", "Roboto-Bold")

_register_chinese_font()

# 全局主题
BG = (0.96, 0.96, 0.97, 1)
PRIMARY = (0.20, 0.45, 0.95, 1)
DANGER = (0.85, 0.30, 0.30, 1)
ORANGE = (0.85, 0.55, 0.10, 1)
GREEN = (0.10, 0.65, 0.30, 1)


class CNLabel(Label):
    def __init__(self, **kw):
        kw.setdefault("font_name", "CN")
        kw.setdefault("font_size", "15sp")
        super().__init__(**kw)


class CNButton(Button):
    def __init__(self, **kw):
        kw.setdefault("font_name", "CN")
        kw.setdefault("font_size", "15sp")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", "48dp")
        super().__init__(**kw)


class CNInput(TextInput):
    def __init__(self, **kw):
        kw.setdefault("font_name", "CN")
        kw.setdefault("font_size", "15sp")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", "44dp")
        kw.setdefault("multiline", False)
        kw.setdefault("background_color", (1, 1, 1, 1))
        super().__init__(**kw)


# ===================== 账户列表主页 =====================
class AccountListScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.api = ApiClient()
        self.search_kw = ""

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        # 顶部标题
        top = BoxLayout(size_hint_y=None, height="48dp", spacing=6)
        top.add_widget(CNLabel(text="多账户管理", bold=True, size_hint_x=0.4, halign="left"))
        self.mode_btn = CNButton(text="管理(×2)", size_hint_x=0.3, bg_color=ORANGE)
        self.mode_btn.bind(on_release=self.toggle_mode)
        top.add_widget(self.mode_btn)
        root.add_widget(top)

        # 搜索
        self.search = CNInput(hint_text="搜索 ID/邮箱/会员名")
        self.search.bind(text=self.on_search)
        root.add_widget(self.search)

        # 操作按钮行
        ops = BoxLayout(size_hint_y=None, height="44dp", spacing=6)
        for txt, cb, color in [
            ("新增", self.add_account, PRIMARY),
            ("刷新余额", self.refresh_all, PRIMARY),
            ("充值", self.recharge, ORANGE),
            ("订单", self.orders, PRIMARY),
            ("刷新Token", self.refresh_token, DANGER),
        ]:
            b = CNButton(text=txt, bg_color=color)
            b.bind(on_release=cb)
            ops.add_widget(b)
        root.add_widget(ops)

        # 账户列表（滚动）
        self.list_scroll = ScrollView()
        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.list_scroll.add_widget(self.list_box)
        root.add_widget(self.list_scroll)

        self.status = CNLabel(text="就绪", size_hint_y=None, height="30dp", color=(0.4,0.4,0.4,1))
        root.add_widget(self.status)

        self.add_widget(root)
        self.selected_id = None
        self.display_mode = db.get_setting("display_mode", "mask")
        self.refresh_mode_btn()

    def on_enter(self):
        self.reload()

    def on_search(self, inst, val):
        self.search_kw = val.strip().lower()
        self.reload()

    def toggle_mode(self, *a):
        self.display_mode = "real" if self.display_mode == "mask" else "mask"
        db.set_setting("display_mode", self.display_mode)
        self.refresh_mode_btn()
        self.reload()

    def refresh_mode_btn(self):
        self.mode_btn.text = "真实" if self.display_mode == "real" else "管理(×2)"

    def reload(self):
        self.list_box.clear_widgets()
        accounts = db.list_accounts()
        if self.search_kw:
            accounts = [a for a in accounts if (self.search_kw in str(a.get("id","")).lower()
                or self.search_kw in (a.get("email") or "").lower()
                or self.search_kw in (a.get("user_name") or "").lower()
                or self.search_kw in (a.get("note") or "").lower())]
        for a in accounts:
            bal = a.get("balance", 0) or 0
            bal_text = f"{bal*2:.3f}" if self.display_mode == "mask" else f"{bal:.3f}"
            row = BoxLayout(orientation="vertical", size_hint_y=None, height="88dp",
                            padding=8, spacing=2)
            with row.canvas.before:
                Color(rgba=(1,1,1,1))
                self._rect = Rectangle(pos=row.pos, size=row.size)
            row.bind(pos=lambda *e: setattr(self._rect, 'pos', row.pos))
            row.bind(size=lambda *e: setattr(self._rect, 'size', row.size))

            line1 = BoxLayout(size_hint_y=None, height="24dp")
            line1.add_widget(CNLabel(text=f"#{a['id']}  {a.get('email','')}", halign="left", bold=True))
            line1.add_widget(CNLabel(text=f"余额: {bal_text}", halign="right", color=(0.9,0.2,0.2,1)))
            row.add_widget(line1)

            line2 = BoxLayout(size_hint_y=None, height="24dp")
            line2.add_widget(CNLabel(text=f"会员: {a.get('user_name','-')}  状态: {a.get('status','idle')}",
                                      halign="left", color=(0.4,0.4,0.4,1)))
            if a.get("note"):
                line2.add_widget(CNLabel(text=a["note"], halign="right", color=(0.4,0.4,0.4,1)))
            row.add_widget(line2)

            row.bind(on_release=lambda inst, aid=a["id"]: self.select(aid))
            self.list_box.add_widget(row)

        self.status.text = f"共 {len(accounts)} 个账户"

    def select(self, aid):
        self.selected_id = aid
        acc = db.get_account(aid)
        if acc:
            popup = Popup(title="账户操作", size_hint=(0.9, 0.6))
            box = BoxLayout(orientation="vertical", padding=10, spacing=8)
            box.add_widget(CNLabel(text=f"{acc['email']}\n余额: {acc.get('balance',0)}"))
            for txt, cb in [
                ("编辑", lambda x: self.edit_account(aid, popup)),
                ("删除", lambda x: self.del_account(aid, popup)),
                ("关闭", lambda x: popup.dismiss()),
            ]:
                b = CNButton(text=txt)
                b.bind(on_release=cb)
                box.add_widget(b)
            popup.content = box
            popup.open()

    def add_account(self, *a):
        self._open_editor(None)

    def edit_account(self, aid, popup):
        popup.dismiss()
        self._open_editor(aid)

    def _open_editor(self, aid):
        acc = db.get_account(aid) if aid else {}
        popup = Popup(title=("编辑账户" if aid else "新增账户"), size_hint=(0.95, 0.9))
        box = BoxLayout(orientation="vertical", padding=10, spacing=6)
        fields = {}
        for label, key, val in [
            ("邮箱", "email", acc.get("email","")),
            ("密码", "password", crypto.decrypt(acc.get("password_enc","")) if acc else ""),
            ("TokenID", "token_id", acc.get("token_id","")),
            ("TokenKey", "token_key", crypto.decrypt(acc.get("token_key_enc","")) if acc else ""),
            ("备注", "note", acc.get("note","")),
        ]:
            box.add_widget(CNLabel(text=label, halign="left", size_hint_y=None, height="24dp"))
            ti = CNInput(text=val)
            fields[key] = ti
            box.add_widget(ti)

        def save(*x):
            email = fields["email"].text.strip()
            if not email:
                return
            db.upsert_account(
                email=email,
                password_enc=crypto.encrypt(fields["password"].text),
                token_id=fields["token_id"].text.strip(),
                token_key_enc=crypto.encrypt(fields["token_key"].text),
                note=fields["note"].text.strip(),
            )
            popup.dismiss()
            self.reload()

        b = CNButton(text="保存", bg_color=PRIMARY)
        b.bind(on_release=save)
        box.add_widget(b)
        popup.content = box
        popup.open()

    def del_account(self, aid, popup):
        popup.dismiss()
        db.delete_account(aid)
        self.reload()

    def _need_selected(self):
        if not self.selected_id:
            self.status.text = "请先在列表中点选一个账户"
            return None
        return db.get_account(self.selected_id)

    def refresh_all(self, *a):
        self.status.text = "正在刷新..."
        def work():
            accounts = db.list_accounts()
            ok = 0
            for acc in accounts:
                if not acc.get("token_id"):
                    continue
                try:
                    tk = crypto.decrypt(acc.get("token_key_enc",""))
                    info = self.api.get_info(acc["token_id"], tk)
                    db.update_account_cache(acc["id"], info["userName"], info["balance"])
                    ok += 1
                except Exception as e:
                    db.set_account_status(acc["id"], f"err")
            Clock.schedule_once(lambda dt: (self.reload(), setattr(self.status, "text", f"刷新完成 {ok}/{len(accounts)}")))
        threading.Thread(target=work, daemon=True).start()

    def recharge(self, *a):
        acc = self._need_selected()
        if not acc: return
        popup = Popup(title="充值", size_hint=(0.9, 0.5))
        box = BoxLayout(orientation="vertical", padding=10, spacing=6)
        box.add_widget(CNLabel(text=f"账户: {acc['email']}\n余额: {acc.get('balance',0)}"))
        amt = CNInput(hint_text="金额，例如 100")
        box.add_widget(amt)
        pay = CNInput(text="alipay", hint_text="alipay / wechat")
        box.add_widget(pay)

        def go(*x):
            try:
                amount = float(amt.text)
            except:
                return
            password = crypto.decrypt(acc.get("password_enc",""))
            try:
                self.api.web_login(acc["email"], password)
                r = self.api.web_recharge_submit(amount, pay.text.strip() or "alipay")
                if r.get("pay_url"):
                    webbrowser.open(r["pay_url"])
                    self.status.text = "已在浏览器打开支付页，支付后回来点刷新余额"
                else:
                    self.status.text = f"未获取到支付链接: {r.get('message')}"
            except Exception as e:
                self.status.text = f"充值失败: {e}"
            popup.dismiss()

        b = CNButton(text="打开支付页", bg_color=ORANGE)
        b.bind(on_release=go)
        box.add_widget(b)
        popup.content = box
        popup.open()

    def orders(self, *a):
        acc = self._need_selected()
        if not acc: return
        password = crypto.decrypt(acc.get("password_enc",""))
        self.status.text = "登录中..."
        def work():
            try:
                self.api.web_login(acc["email"], password)
                resp = self.api.web_get_orders(page=1, row=100)
                for o in resp.get("list", []):
                    db.upsert_order(acc["id"], o)
                Clock.schedule_once(lambda dt: self._open_orders(acc))
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self.status, "text", f"订单加载失败: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _open_orders(self, acc):
        orders = db.list_orders(acc["id"])
        popup = Popup(title=f"订单 ({len(orders)})", size_hint=(0.98, 0.9))
        box = BoxLayout(orientation="vertical", padding=6, spacing=4)
        scroll = ScrollView()
        lb = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
        lb.bind(minimum_height=lb.setter("height"))
        for o in orders:
            row = BoxLayout(orientation="vertical", size_hint_y=None, height="64dp", padding=4)
            with row.canvas.before:
                Color(rgba=(1,1,1,1))
                Rectangle(pos=row.pos, size=row.size)
            row.add_widget(CNLabel(text=f"{o.get('order_id','')}  ¥{o.get('order_price','')}", halign="left", font_size="13sp"))
            row.add_widget(CNLabel(text=f"{o.get('order_goods_name','')}  {o.get('order_date','')}",
                                   halign="left", color=(0.4,0.4,0.4,1), font_size="12sp"))
            row.bind(on_release=lambda inst, oid=o.get("order_id"): self._open_detail(acc, oid))
            lb.add_widget(row)
        scroll.add_widget(lb)
        box.add_widget(scroll)
        b = CNButton(text="关闭")
        b.bind(on_release=lambda x: popup.dismiss())
        box.add_widget(b)
        popup.content = box
        popup.open()

    def _open_detail(self, acc, order_id):
        self.status.text = "加载详情..."
        def work():
            try:
                d = self.api.web_get_order_detail(order_id)
                l = self.api.web_get_order_code_log(order_id)
                Clock.schedule_once(lambda dt: self._show_detail(d, l))
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self.status, "text", f"详情失败: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _show_detail(self, detail, log):
        d = detail.get("data") or {}
        popup = Popup(title="订单详情", size_hint=(0.98, 0.95))
        box = BoxLayout(orientation="vertical", padding=10, spacing=4)
        scroll = ScrollView()
        lb = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
        lb.bind(minimum_height=lb.setter("height"))

        def add_row(k, v):
            r = BoxLayout(size_hint_y=None, height="32dp")
            r.add_widget(CNLabel(text=k, halign="left", color=(0.4,0.4,0.4,1), size_hint_x=0.35))
            r.add_widget(CNLabel(text=str(v) if v not in (None,"") else "-", halign="left", size_hint_x=0.65))
            lb.add_widget(r)

        add_row("订单号", d.get("orderId"))
        add_row("下单时间", d.get("createTime"))
        add_row("完成时间", d.get("orderEndTime"))
        add_row("商品名称", d.get("orderGname"))
        add_row("商品单价", d.get("orderGprice"))
        add_row("订单金额", d.get("orderPrice"))
        add_row("订单数量", d.get("orderNum"))
        add_row("当前数量", d.get("orderEndNum"))
        add_row("下单IP", d.get("ip"))
        add_row("状态", d.get("orderCode"))

        # 下单内容
        import json as _json
        ov_raw = d.get("orderValue")
        if ov_raw:
            try:
                ov = _json.loads(ov_raw)
                for k, v in ov.items():
                    add_row(k, v)
            except:
                add_row("下单内容", ov_raw)

        scroll.add_widget(lb)
        box.add_widget(scroll)
        b = CNButton(text="关闭")
        b.bind(on_release=lambda x: popup.dismiss())
        box.add_widget(b)
        popup.content = box
        popup.open()

    def refresh_token(self, *a):
        acc = self._need_selected()
        if not acc: return
        password = crypto.decrypt(acc.get("password_enc",""))
        self.status.text = "正在刷新token..."
        def work():
            try:
                self.api.web_login(acc["email"], password)
                new_t = self.api.refresh_token()
                db.update_account_token(acc["id"], new_t["tokenId"], crypto.encrypt(new_t["tokenKey"]))
                Clock.schedule_once(lambda dt: (self.reload(), setattr(self.status, "text", f"Token已更新: {new_t['tokenId']}")))
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self.status, "text", f"刷新token失败: {e}"))
        threading.Thread(target=work, daemon=True).start()


class AccountApp(App):
    def build(self):
        db.init_db()
        sm = ScreenManager()
        s = AccountListScreen(name="main")
        sm.add_widget(s)
        return sm


if __name__ == "__main__":
    AccountApp().run()
