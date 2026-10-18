# 多账户管理工具 - 安卓版（Kivy）

## 关键说明
- 已内置中文字体加载逻辑，只要 `NotoSansSC-Regular.otf` 放在项目根目录，中文就不会显示成方框。
- 所有桌面端业务逻辑（API 对接、SQLite 加密存储、token 刷新、订单查询、充值跳转）全部复用。

## 一键出 APK（GitHub Actions，推荐）
1. 把整个 `account_manager_mobile` 目录推到一个 GitHub 仓库
2. 仓库 Settings → Actions → 允许所有操作
3. 点 Actions 标签 → 选 "Build APK" → Run workflow
4. 等 20–40 分钟，构建完成后在该次运行页面底部下载 `account-manager-apk` 压缩包，里面就是 `.apk`

`.github/workflows/build.yml` 已经写好：
- 自动装 JDK17 + Android SDK/NDK
- 自动下载 Noto Sans SC 中文字体
- 自动跑 buildozer 产出 debug APK

## 本地构建（Ubuntu/WSL）
```bash
sudo apt update
sudo apt install -y openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev \
  libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev
pip install buildozer cython==0.29.33

# 下载中文字体
wget -O NotoSansSC-Regular.otf \
  "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"

buildozer android debug
# 产物在 bin/*.apk
```

## 功能
- 账户列表（搜索、新增、编辑、删除）
- 余额显示切换：真实 / 管理模式（×2）
- 一键刷新全部余额
- 选中账户充值：手机浏览器打开支付页
- 订单列表 + 详情（自动 web 登录 → getData 拉订单 → queryOrderDetail 看详情）
- 一键刷新 token（web 登录 → setToken → getuserInfo → 写库）

## 已解决中文乱码
- `main.py` 启动时按顺序找 `NotoSansSC-Regular.otf`、`/system/fonts/NotoSansCJK-Regular.ttc`、`/system/fonts/DroidSansFallback.ttf`
- 找到就注册为全局 `CN` 字体，所有 Label/Button/Input 都用 `CN`
- GitHub Actions 构建时已自动下载字体到根目录
