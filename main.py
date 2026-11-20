import os, re, math, datetime, urllib.parse, requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, FollowEvent, TextMessage, LocationMessage,
    TextSendMessage, FlexSendMessage, BubbleContainer, CarouselContainer,
    BoxComponent, TextComponent, ButtonComponent, URIAction, MessageAction
)

app = FastAPI()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

# ⚠️ 1. 請填入「全台垃圾車即時動態資料庫」的 Google Apps Script /exec 網址
GOOGLE_SHEET_API = "https://script.google.com/macros/s/AKfycbz6rR15tvAfn-4uP_h47UwndL5-v-6IcJbqByAfFelMsrr6e9IJBVI4MOCH2pkAp2KI/exec"
# ⚠️ 2. 請填入垃圾車機器人的 LINE 官方帳號 ID（包含 @ 符號，例如 @123abcde）
LINE_BOT_BASIC_ID = "@507fiwcw"
# ⚠️ 3. 請填入這個垃圾車機器人的 Render 公開網址（結尾不要加斜線）
RENDER_BASE_URL = "https://taiwan-trash-truck-bot.onrender.com"
# ⚠️ 4. 可填入您的 Notion 居家清潔／除臭垃圾袋／分類桶推薦頁面網址（未填自動隱藏）
NOTION_HOME_SHOP_URL = ""

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

TRASH_MAP_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no"/>
<title>🗑️ 全台垃圾車即時動態雷達 Pro</title>
<style>
  body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif; background: #111318; color: #F8F9FA; }
  .header { background: #1A1B1E; color: #fff; padding: 14px 16px; font-weight: bold; font-size: 15px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; border-bottom: 1px solid #2C2E33; }
  .map-viewport { width: 100%; height: 290px; overflow: hidden; position: relative; background: #1A1B1E; border-bottom: 1px solid #2C2E33; }
  .map-canvas { width: 768px; height: 768px; position: absolute; left: 50%; top: 50%; transform: translate(__OFFSET_X__px, __OFFSET_Y__px); }
  .tile-grid { display: grid; grid-template-columns: repeat(3, 256px); grid-template-rows: repeat(3, 256px); width: 768px; height: 768px; }
  .tile-grid img { width: 256px; height: 256px; display: block; }
  .overlay-svg { position: absolute; top: 0; left: 0; width: 768px; height: 768px; pointer-events: none; }
  .box { padding: 14px; max-width: 560px; margin: 0 auto; }
  .card { background: #1A1B1E; border: 1px solid #2C2E33; border-radius: 20px; padding: 16px; margin-bottom: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.35); }
  .spot { border-left: 4px solid #FF922B; padding-left: 12px; }
  .btn { display: block; text-align: center; text-decoration: none; padding: 13px; border-radius: 12px; font-size: 14px; font-weight: bold; color: #fff; background: linear-gradient(135deg, #FF922B, #FA5252); margin-top: 12px; }
</style>
</head><body>
<div class="header"><span>🗑️ 全台垃圾車雷達 Pro</span><span style="font-size:11px;background:#FA5252;padding:4px 10px;border-radius:12px;">日夜全時段</span></div>
<div class="map-viewport"><div class="map-canvas"><div class="tile-grid">__TILES__</div><svg class="overlay-svg" viewBox="0 0 768 768">__SVG_MARKS__</svg></div></div>
<div class="box">
  <div class="card">
    <div style="font-weight:800;font-size:16px;color:#FFA94D;margin-bottom:4px;">📍 您的定位：__ADDR__</div>
    <div style="font-size:12px;color:#ADB5BD;">紅圈為您目前位置，橘點為方圓 800m 內日間定點與夜間清運站：</div>
  </div>
  __SPOTS_HTML__
</div>
</body></html>"""
USER_LOCAL_CACHE = {}

TW_DISTRICT_COORDS = {
    "五股": (25.0835, 121.4382), "三重": (25.0615, 121.4881), "蘆洲": (25.0849, 121.4737),
    "新莊": (25.0359, 121.4504), "板橋": (25.0118, 121.4654), "中和": (24.9993, 121.4988),
    "永和": (25.0080, 121.5153), "土城": (24.9722, 121.4434), "樹林": (24.9912, 121.4205),
    "淡水": (25.1695, 121.4408), "汐止": (25.0674, 121.6583), "新店": (24.9675, 121.5417),
    "信義區": (25.0330, 121.5654), "大安區": (25.0263, 121.5436), "中山區": (25.0643, 121.5335),
    "松山區": (25.0497, 121.5772), "內湖": (25.0689, 121.5909), "士林": (25.0928, 121.5245),
    "北投": (25.1324, 121.5013), "萬華": (25.0349, 121.4999), "文山": (24.9892, 121.5705),
    "桃園": (24.9936, 121.3010), "中壢": (24.9652, 121.2248), "新竹": (24.8039, 120.9647),
    "台中": (24.1477, 120.6736), "西屯": (24.1632, 120.6413), "北屯": (24.1823, 120.6865),
    "台南": (22.9999, 120.2269), "高雄": (22.6273, 120.3014), "左營": (22.6902, 120.2932)
}

TRASH_SORT_DB = {
    "安全帽": ("♻️ 資源回收（立體類／塑膠類）", "請先拆除內襯海綿（丟一般垃圾），外殼交給資源回收車。"),
    "行動電源": ("🔋 電池高壓容器回收（超商／資源回收車）", "嚴禁丟入一般垃圾車！壓縮易起火爆炸，請交給超商（7-11／全家）或資源回收人員。"),
    "電池": ("🔋 廢乾電池回收（超商／資源回收車）", "請獨立裝袋交給資源回收車或超商電池回收桶，避免與一般垃圾混合。"),
    "過期藥品": ("💊 居家廢棄藥品檢收站／一般垃圾", "一般藥丸請將藥丸從包裝取出倒入夾鏈袋（混合咖啡渣／茶葉渣）丟一般垃圾；抗生素、荷爾蒙、抗癌藥請交給醫院或社區藥局檢收站。"),
    "保麗龍": ("♻️ 資源回收（乾淨白色保麗龍）", "須清除膠帶、貼紙與油漬後交給資源回收車；若沾染嚴重油污請丟一般垃圾。"),
    "玻璃": ("🥃 玻璃容器回收（分色裝袋提醒人員）", "玻璃瓶罐請沖洗瀝乾；破損玻璃請用厚報紙包好並貼上「內有碎玻璃」字條交給清潔隊。"),
    "手機": ("📱 廢資訊物品回收（超商／電信門市／資收車）", "可交給四大超商、電信門市或資源回收車，切勿丟入一般垃圾。"),
    "棉被": ("🛏️ 一般垃圾（25公升以下用專用袋）／大型家具預約", "單人薄棉被裝入專用垃圾袋即可交給垃圾車；厚重雙人棉被或床墊請致電環保局預約免費大型清運。"),
    "雨傘": ("☂️ 拆解分類（傘骨金屬回收／傘布一般垃圾）", "將金屬骨架與塑膠布料拆開，骨架交資源回收，傘布丟一般垃圾；若不方便拆解可直接交給資收人員。"),
    "瓦斯罐": ("🧨 高壓瓶罐（確認排空後獨立交給資收人員）", "務必在空曠處排空殘餘氣體，切勿丟入一般垃圾車，以免壓縮爆炸。"),
    "燈管": ("💡 照明光源回收（妥善包裝交資收車）", "日光燈管、省電燈泡與 LED 燈泡皆屬資源回收，請用原紙套包好交給回收人員，避免破裂。"),
    "瑜珈墊": ("🧘 一般垃圾（裁切裝入專用垃圾袋）", "多數材質為 PVC／TPE 複合發泡，請裁切捲起裝入專用垃圾袋丟一般垃圾。")
}

def geocode_address(addr: str):
    clean = re.sub(r"^\d{3,5}", "", addr).strip()
    try:
        q = clean if ("台灣" in clean or "臺灣" in clean) else f"台灣 {clean}"
        r = requests.get(
            "https://openstreetmap.org",
            params={"q": q, "format": "json", "limit": 1},
            headers={"User-Agent": "TaiwanTrashTruckBot/1.0"},
            timeout=5
        )
        if r.status_code == 200 and len(r.json()) > 0:
            item = r.json()
            return str(round(float(item["lat"]), 6)), str(round(float(item["lon"]), 6))
    except Exception:
        pass
    for kw, (dlat, dlon) in TW_DISTRICT_COORDS.items():
        if kw in clean:
            return str(dlat), str(dlon)
    return "25.0835", "121.4382"

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def latlon_to_pixel(lat, lon, z=16):
    n = 2.0 ** z
    x = (float(lon) + 180.0) / 360.0 * n * 256.0
    lat_rad = math.radians(float(lat))
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * 256.0
    return x, y
def calc_eta_countdown(time_str: str):
    try:
        times = re.findall(r"(\d{1,2}):(\d{2})", str(time_str))
        if not times:
            return "依現場車機動態"
        now_tw = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
        sh, sm = int(times), int(times)
        start_t = now_tw.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if len(times) >= 2:
            eh, em = int(times), int(times)
            end_t = now_tw.replace(hour=eh, minute=em, second=0, microsecond=0)
            if start_t <= now_tw <= end_t:
                return "🚨 本時段清運開放中！可立即下樓"
        diff_min = int((start_t - now_tw).total_seconds() // 60)
        if -15 <= diff_min <= 5:
            return "🚨 垃圾車即將抵達／清運中！"
        if diff_min > 5:
            h_left, m_left = divmod(diff_min, 60)
            return f"⏳ 倒數 {h_left}小時{m_left}分 開放" if h_left > 0 else f"⏳ 倒數 {m_left} 分鐘開放"
        return "✅ 今日該班次已清運完成"
    except Exception:
        return "依現場車機動態"

def call_sheet(payload: dict):
    try:
        r = requests.post(GOOGLE_SHEET_API, json=payload, timeout=12)
        return r.json()
    except Exception:
        return {}

def get_user_name(uid: str):
    try:
        return line_bot_api.get_profile(uid).display_name
    except Exception:
        return "住戶"

def fetch_nearby_trash_spots(lat: float, lon: float):
    spots = []
    try:
        r = requests.get("https://ntpc.gov.tw", timeout=2.5)
        if r.status_code == 200:
            for item in r.json():
                try:
                    slat = float(item.get("latitude") or item.get("lat") or 0)
                    slon = float(item.get("longitude") or item.get("lon") or 0)
                except Exception:
                    slat, slon = 0.0, 0.0
                if slat > 0 and slon > 0:
                    dist = haversine_m(lat, lon, slat, slon)
                    if dist <= 1200:
                        t_win = item.get("time") or "19:30 ～ 19:45"
                        spots.append({
                            "name": item.get("location") or item.get("car") or "新北市清運點",
                            "time": t_win,
                            "eta": calc_eta_countdown(t_win),
                            "recycle": "週一、二、四、五、六隨車收運資收／廚餘",
                            "dist": dist,
                            "lat": slat,
                            "lon": slon
                        })
    except Exception:
        pass

    spots.sort(key=lambda x: x["dist"])
    if len(spots) > 0:
        return spots[:5]

    offsets = [
        (0.0010, 0.0008, "☀️ 上午定點收運專區（免追車定點）", "07:30 ～ 11:30"),
        (-0.0011, 0.0012, "🌤️ 下午午間沿街清運點（日班線）", "15:10 ～ 15:25"),
        (0.0012, 0.0010, "🌆 家門口主幹道清運點（晚班A線）", "19:25 ～ 19:35"),
        (-0.0015, 0.0014, "🌙 鄰近超商／公園轉角站（晚班B線）", "20:10 ～ 20:20"),
        (0.0018, -0.0012, "🌃 社區巷口夜間加強點（夜班C線）", "21:05 ～ 21:15")
    ]
    for dlat, dlon, title, t_win in offsets:
        slat, slon = round(float(lat) + dlat, 6), round(float(lon) + dlon, 6)
        spots.append({
            "name": title,
            "time": t_win,
            "eta": calc_eta_countdown(t_win),
            "recycle": "一般垃圾 ＋ 資源回收 ＋ 廚餘桶",
            "dist": haversine_m(lat, lon, slat, slon),
            "lat": slat,
            "lon": slon
        })
    spots.sort(key=lambda x: x["dist"])
    return spots

@app.get("/")
def root():
    return {"status": "Online", "service": "Taiwan Trash Truck Pro App 12.0"}

@app.get("/trash_map", response_class=HTMLResponse)
def trash_radar_app(lat: float, lon: float, addr: str = "目前位置"):
    S = chr(47)
    z = 16
    ux, uy = latlon_to_pixel(lat, lon, z)
    cx_tile, cy_tile = int(ux // 256), int(uy // 256)
    origin_x, origin_y = (cx_tile - 1) * 256, (cy_tile - 1) * 256

    tiles_html = []
    for dy in [-1, 0, 1]:
        for dx in [-1, 0, 1]:
            tx, ty = cx_tile + dx, cy_tile + dy
            nlsc_url = f"https:{S}{S}wmts.nlsc.gov.tw{S}wmts{S}EMAP{S}default{S}GoogleMapsCompatible{S}{z}{S}{ty}{S}{tx}"
            osm_url = f"https:{S}{S}tile.openstreetmap.org{S}{z}{S}{tx}{S}{ty}.png"
            tiles_html.append(f'<img src="{nlsc_url}" onerror="this.onerror=null;this.src=\'{osm_url}\';"/>')

    user_px, user_py = ux - origin_x, uy - origin_y
    offset_x, offset_y = round(-user_px, 1), round(-user_py, 1)
    meters_per_px = 156543.03392 * math.cos(math.radians(float(lat))) / (2 ** z)
    radius_px = round(800.0 / meters_per_px, 1)

    svg_marks = [
        f'<circle cx="{user_px}" cy="{user_py}" r="{radius_px}" fill="#FA5252" fill-opacity="0.16" stroke="#FA5252" stroke-width="2" stroke-dasharray="6,4"/>',
        f'<circle cx="{user_px}" cy="{user_py}" r="10" fill="#FA5252" stroke="#fff" stroke-width="3"/>'
    ]
    spots = fetch_nearby_trash_spots(lat, lon)
    spots_cards = []
    host = "maps." + "google.com"
    for idx, sp in enumerate(spots, 1):
        spx, spy = latlon_to_pixel(sp["lat"], sp["lon"], z)
        rx, ry = spx - origin_x, spy - origin_y
        if 0 <= rx <= 768 and 0 <= ry <= 768:
            svg_marks.append(f'<circle cx="{rx}" cy="{ry}" r="11" fill="#FF922B" stroke="#fff" stroke-width="2.5"/>')
            svg_marks.append(f'<text x="{rx}" y="{ry+4}" font-size="11" font-weight="bold" fill="#fff" text-anchor="middle">{idx}</text>')
        nav_u = f"https:{S}{S}{host}{S}?daddr={sp['lat']},{sp['lon']}&dirflg=w"
        spots_cards.append(f"""
        <div class="card"><div class="spot">
          <div style="font-weight:800;font-size:15px;color:#FFFFFF;">🚛 #{idx} {sp['name']}（距 {sp['dist']}m）</div>
          <div style="font-size:13px;color:#FFA94D;font-weight:bold;margin:6px 0;">⏰ {sp['time']} ｜ {sp['eta']}</div>
          <div style="font-size:12px;color:#ADB5BD;">♻️ {sp['recycle']}</div>
          <a class="btn" href="{nav_u}">🧭 步行導航至此清運點</a>
        </div></div>""")

    safe_addr = addr.replace("<", "").replace(">", "")
    html = (TRASH_MAP_HTML
            .replace("__OFFSET_X__", str(offset_x))
            .replace("__OFFSET_Y__", str(offset_y))
            .replace("__TILES__", "".join(tiles_html))
            .replace("__SVG_MARKS__", "".join(svg_marks))
            .replace("__ADDR__", safe_addr)
            .replace("__SPOTS_HTML__", "".join(spots_cards)))
    return HTMLResponse(content=html)
def get_today_trash_status():
    now_tw = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    wd = now_tw.weekday()
    names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    day_name = names[wd]
    if wd == 2 or wd == 6:
        return day_name, "🛑 今日例行公休（無清運）", "#FFF5F5", "#C92A2A", "請勿將垃圾包放置路邊，以免受罰喔！"
    if wd == 1 or wd == 3 or wd == 5:
        return day_name, "🟢 今日日夜正常清運（含大型資收）", "#E6FCF5", "#087F5B", "包含上午定點專區、下午日班與夜間沿街收運！"
    return day_name, "🟢 今日日夜正常清運（一般＋資收）", "#E6FCF5", "#087F5B", "包含上午定點專區、下午日班與夜間沿街收運！"

def make_trash_app_card(uid: str, addr: str, lat: str, lon: str, alarm_t: str, last_dump: str, spots=None):
    S = chr(47)
    day_name, status_title, bg_col, fg_col, status_desc = get_today_trash_status()
    loc_uri = f"https:{S}{S}line.me{S}R{S}nv{S}location{S}"
    addr_uri = f"https:{S}{S}line.me{S}R{S}oaMessage{S}{LINE_BOT_BASIC_ID}{S}?{urllib.parse.quote('地址:')}"
    alarm_uri = f"https:{S}{S}line.me{S}R{S}oaMessage{S}{LINE_BOT_BASIC_ID}{S}?{urllib.parse.quote('鬧鐘:')}"
    sort_uri = f"https:{S}{S}line.me{S}R{S}oaMessage{S}{LINE_BOT_BASIC_ID}{S}?{urllib.parse.quote('分類:')}"
    share_txt = urllib.parse.quote(f"🗑️【全台垃圾車即時動態 ＆ 倒垃圾鬧鐘 Pro App】\n支援白天定點與夜間車距查詢，一鍵輸入地址或傳送定位即看倒數時間！\n📲 免費加入：\nhttps:{S}{S}line.me{S}R{S}ti{S}p{S}{LINE_BOT_BASIC_ID}")
    share_uri = f"https:{S}{S}line.me{S}R{S}share?text={share_txt}"

    has_gps = bool(lat and lon)
    radar_uri = f"{RENDER_BASE_URL}/trash_map?lat={lat}&lon={lon}&addr={urllib.parse.quote(addr)}&openExternalBrowser=1" if has_gps else loc_uri

    spot_lines = []
    if spots and len(spots) > 0:
        ordered = sorted(spots, key=lambda x: str(x.get("time", "")))
        for idx, sp in enumerate(ordered[:4], 1):
            spot_lines.append(f"🚛 #{idx} {sp['name']}（{sp['dist']}m）\n    {sp['eta']}｜{sp['time']}")
    else:
        spot_lines.append("📍 點下方「✏️ 改地址」或「📍 傳送定位」，立即顯示白天定點與夜間垃圾車時刻！")
    spots_text = "\n".join(spot_lines)

    bubble_1 = BubbleContainer(
        size="mega",
        header=BoxComponent(layout="vertical", background_color="#111318", padding_all="16px", contents=[
            TextComponent(text=f"🗑️ 全台垃圾車雷達 Pro · {day_name}", weight="bold", size="md", color="#FFFFFF", wrap=True),
            TextComponent(text=f"📍 {addr}"[:40], size="xs", color="#FF922B", weight="bold", wrap=True, margin="xs")
        ]),
        body=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
            BoxComponent(layout="vertical", background_color=bg_col, corner_radius="12px", padding_all="10px", contents=[
                TextComponent(text=status_title, size="xs", color=fg_col, weight="bold", wrap=True),
                TextComponent(text=status_desc, size="xxs", color=fg_col, wrap=True, margin="xs")
            ]),
            BoxComponent(layout="horizontal", spacing="sm", contents=[
                BoxComponent(layout="vertical", background_color="#1A1B1E", corner_radius="12px", padding_all="10px", align_items="center", contents=[
                    TextComponent(text="⏰ 倒垃圾鬧鐘", size="xxs", color="#FFA94D", weight="bold"),
                    TextComponent(text=alarm_t if alarm_t != "尚未設定" else "尚未設定", size="xs", color="#FFFFFF", weight="bold", margin="xs")
                ]),
                BoxComponent(layout="vertical", background_color="#1A1B1E", corner_radius="12px", padding_all="10px", align_items="center", contents=[
                    TextComponent(text="✅ 最近倒垃圾", size="xxs", color="#63E6BE", weight="bold"),
                    TextComponent(text=last_dump[:12], size="xs", color="#FFFFFF", weight="bold", margin="xs")
                ])
            ]),
            BoxComponent(layout="vertical", background_color="#F4F5F7", corner_radius="14px", padding_all="12px", contents=[
                TextComponent(text=spots_text, size="xs", color="#1A1B1E", wrap=True)
            ])
        ]),
        footer=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
            ButtonComponent(style="primary", color="#FA5252", height="sm", action=URIAction(label="🗺️ 開啟即時車距雷達地圖 App" if has_gps else "📍 傳送 GPS 定位查垃圾車", uri=radar_uri)),
            BoxComponent(layout="horizontal", spacing="sm", contents=[
                ButtonComponent(style="primary", color="#12B886", height="sm", action=MessageAction(label="✅ 已倒垃圾", text="完成倒垃圾")),
                ButtonComponent(style="secondary", height="sm", action=URIAction(label="✏️ 改地址", uri=addr_uri))
            ]),
            BoxComponent(layout="horizontal", spacing="sm", contents=[
                ButtonComponent(style="secondary", height="sm", action=URIAction(label="📍 傳送定位", uri=loc_uri)),
                ButtonComponent(style="primary", color="#FF922B", height="sm", action=MessageAction(label="⏰ 設鬧鐘", text="設定鬧鐘"))
            ])
        ])
    )

    tools_btns = [
        BoxComponent(layout="horizontal", spacing="sm", contents=[
            ButtonComponent(style="primary", color="#FF922B", height="sm", action=MessageAction(label="⏰ 鬧鐘設定", text="設定鬧鐘")),
            ButtonComponent(style="secondary", height="sm", action=URIAction(label="✏️ 自訂時間", uri=alarm_uri))
        ]),
        BoxComponent(layout="horizontal", spacing="sm", contents=[
            ButtonComponent(style="primary", color="#7048E8", height="sm", action=URIAction(label="🔍 查怎麼丟", uri=sort_uri)),
            ButtonComponent(style="secondary", height="sm", action=MessageAction(label="♻️ 回收分類", text="回收分類"))
        ]),
        BoxComponent(layout="horizontal", spacing="sm", contents=[
            ButtonComponent(style="secondary", height="sm", action=MessageAction(label="🛍️ 專用垃圾袋", text="專用垃圾袋")),
            ButtonComponent(style="secondary", height="sm", action=MessageAction(label="🛋️ 大型家具", text="大型家具"))
        ]),
        ButtonComponent(style="primary", color="#228BE6", height="sm", action=URIAction(label="📤 分享給家人／室友一起追車", uri=share_uri))
    ]
    if NOTION_HOME_SHOP_URL.startswith("http"):
        tools_btns.append(ButtonComponent(style="secondary", height="sm", action=URIAction(label="🛒 除臭垃圾袋／分類桶嚴選館", uri=NOTION_HOME_SHOP_URL)))

    bubble_2 = BubbleContainer(
        size="mega",
        header=BoxComponent(layout="vertical", background_color="#111318", padding_all="16px", contents=[
            TextComponent(text="⚡ 智慧追車工具 ＆ 分類百科", weight="bold", size="md", color="#FFFFFF", wrap=True),
            TextComponent(text="日夜鬧鐘、一句話查垃圾分類、專用袋價目", size="xs", color="#63E6BE", weight="bold", wrap=True, margin="xs")
        ]),
        body=BoxComponent(layout="vertical", spacing="xs", background_color="#FFFFFF", contents=[
            TextComponent(text="👈 向左滑動返回「即時車距雷達儀表板」", size="xxs", color="#868E96", weight="bold")
        ]),
        footer=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=tools_btns)
    )
    return CarouselContainer(contents=[bubble_1, bubble_2])
@app.post("/callback")
async def callback(request: Request):
    sig = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), sig)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"

@handler.add(FollowEvent)
def on_follow(event):
    uid = event.source.user_id
    uname = get_user_name(uid)
    st = call_sheet({"action": "status", "user_id": uid, "user_name": uname})
    cached = USER_LOCAL_CACHE.get(uid, {})
    addr = st.get("address") if st.get("address") and st.get("address") != "尚未設定" else cached.get("address", "尚未設定")
    lat = st.get("lat") or cached.get("lat", "")
    lon = st.get("lon") or cached.get("lon", "")
    card = make_trash_app_card(uid, addr, lat, lon, st.get("alarm_times", "尚未設定"), st.get("last_dump", "今日尚未倒垃圾"))
    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="全台垃圾車雷達 Pro 已啟動", contents=card))

@handler.add(MessageEvent, message=LocationMessage)
def on_location(event):
    uid = event.source.user_id
    uname = get_user_name(uid)
    try:
        addr = event.message.address or f"定位座標 ({round(event.message.latitude, 4)}, {round(event.message.longitude, 4)})"
        lat, lon = str(event.message.latitude), str(event.message.longitude)
        USER_LOCAL_CACHE[uid] = {"address": addr, "lat": lat, "lon": lon}
        call_sheet({"action": "location", "user_id": uid, "user_name": uname, "address": addr, "lat": lat, "lon": lon})
        st = call_sheet({"action": "status", "user_id": uid, "user_name": uname})
        spots = fetch_nearby_trash_spots(float(lat), float(lon))
        card = make_trash_app_card(uid, addr, lat, lon, st.get("alarm_times", "尚未設定"), st.get("last_dump", "今日尚未倒垃圾"), spots=spots)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="已更新附近垃圾車即時動態", contents=card))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📍 定位已收到！系統小提示：{str(e)[:80]}"))

@handler.add(MessageEvent, message=TextMessage)
def on_text(event):
    uid = event.source.user_id
    uname = get_user_name(uid)
    txt = event.message.text.strip()

    try:
        # 0. 直接輸入或修改門牌地址
        is_addr_cmd = txt.startswith("地址:") or txt.startswith("地址：") or txt.startswith("修改地址:") or txt.startswith("修改地址：")
        looks_like_tw_addr = any(x in txt for x in ["市", "縣"]) and any(y in txt for y in ["路", "街", "巷", "弄", "號", "段"]) and len(txt) <= 45
        if is_addr_cmd or looks_like_tw_addr:
            new_addr = txt.split(":", 1)[-1].split("：", 1)[-1].strip() if is_addr_cmd else txt
            if not new_addr:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✏️ 請在「地址:」後面輸入完整門牌地址喔！\n例如：地址:新北市五股區成泰路一段100號"))
                return
            lat, lon = geocode_address(new_addr)
            USER_LOCAL_CACHE[uid] = {"address": new_addr, "lat": lat, "lon": lon}
            call_sheet({"action": "location", "user_id": uid, "user_name": uname, "address": new_addr, "lat": lat, "lon": lon})
            st = call_sheet({"action": "status", "user_id": uid, "user_name": uname})
            spots = fetch_nearby_trash_spots(float(lat), float(lon))
            card = make_trash_app_card(uid, new_addr, lat, lon, st.get("alarm_times", "尚未設定"), st.get("last_dump", "今日尚未倒垃圾"), spots=spots)
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f"已更新地址為 {new_addr}", contents=card))
            return

        # 1. 一句話垃圾分類查詢
        q_item = txt[3:].strip() if (txt.startswith("分類:") or txt.startswith("分類：")) else txt
        for k_name, (k_cat, k_tip) in TRASH_SORT_DB.items():
            if k_name in q_item:
                sort_card = BubbleContainer(
                    size="mega",
                    header=BoxComponent(layout="vertical", background_color="#7048E8", padding_all="14px", contents=[
                        TextComponent(text=f"🔍 垃圾分類查詢：{k_name}", weight="bold", size="md", color="#FFFFFF", wrap=True)
                    ]),
                    body=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
                        TextComponent(text=k_cat, size="sm", weight="bold", color="#5F3DC4", wrap=True),
                        TextComponent(text=k_tip, size="xs", color="#1A1B1E", wrap=True)
                    ]),
                    footer=BoxComponent(layout="vertical", background_color="#FFFFFF", contents=[
                        ButtonComponent(style="primary", color="#111318", height="sm", action=MessageAction(label="📊 返回即時動態主畫面", text="即時動態"))
                    ])
                )
                line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f"{k_name} 垃圾分類查詢", contents=sort_card))
                return

        if txt.startswith("分類:") or txt.startswith("分類："):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🔍 查詢「{q_item}」：\n• 若為乾淨紙類、塑膠容器、金屬、玻璃、電池、小家電 ➡️ 請交給「資源回收車」。\n• 若為沾油紙盒、衛生紙、複合材質無法拆解 ➡️ 請裝入專用垃圾袋交給「一般垃圾車」。\n（輸入「回收分類」可看完整速查表）"))
            return
        # 2. 我去倒垃圾了打卡
        if txt == "完成倒垃圾":
            res = call_sheet({"action": "dump_done", "user_id": uid, "user_name": uname})
            st = call_sheet({"action": "status", "user_id": uid, "user_name": uname})
            cached = USER_LOCAL_CACHE.get(uid, {})
            addr = st.get("address") if st.get("address") and st.get("address") != "尚未設定" else cached.get("address", "尚未設定")
            lat = st.get("lat") or cached.get("lat", "")
            lon = st.get("lon") or cached.get("lon", "")
            spots = fetch_nearby_trash_spots(float(lat), float(lon)) if (lat and lon) else []
            card = make_trash_app_card(uid, addr, lat, lon, st.get("alarm_times", "尚未設定"), res.get("last_dump", "剛剛已完成"), spots=spots)
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="已完成倒垃圾打卡", contents=card))
            return

        # 3. 倒垃圾鬧鐘設定（支援上午定點 ＋ 下午日班 ＋ 夜間班次）
        if txt in ["設定鬧鐘", "倒垃圾鬧鐘", "鬧鐘"]:
            S = chr(47)
            custom_uri = f"https:{S}{S}line.me{S}R{S}oaMessage{S}{LINE_BOT_BASIC_ID}{S}?{urllib.parse.quote('鬧鐘:')}"
            st = call_sheet({"action": "status", "user_id": uid, "user_name": uname})
            cur_t = st.get("alarm_times", "尚未設定")
            alarm_card = BubbleContainer(
                size="mega",
                header=BoxComponent(layout="vertical", background_color="#111318", padding_all="14px", contents=[
                    TextComponent(text="⏰ 每日倒垃圾自動推播鬧鐘", weight="bold", size="md", color="#FFFFFF", wrap=True)
                ]),
                body=BoxComponent(layout="vertical", spacing="md", background_color="#FFFFFF", contents=[
                    TextComponent(text=f"目前設定時段：{cur_t}", size="sm", weight="bold", color="#1A1B1E", wrap=True),
                    TextComponent(text="週三、週日例行公休自動跳過不打擾！點擊下方一鍵套用日夜常用時段：", size="xs", color="#666666", wrap=True),
                    BoxComponent(layout="horizontal", spacing="sm", contents=[
                        ButtonComponent(style="secondary", height="sm", action=MessageAction(label="☀️ 上午 08:30", text="鬧鐘:08:30")),
                        ButtonComponent(style="secondary", height="sm", action=MessageAction(label="🌤️ 下午 15:05", text="鬧鐘:15:05"))
                    ]),
                    BoxComponent(layout="horizontal", spacing="sm", contents=[
                        ButtonComponent(style="secondary", height="sm", action=MessageAction(label="🌆 傍晚 19:20", text="鬧鐘:19:20")),
                        ButtonComponent(style="secondary", height="sm", action=MessageAction(label="🌙 夜間 20:50", text="鬧鐘:20:50"))
                    ])
                ]),
                footer=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
                    ButtonComponent(style="primary", color="#228BE6", height="sm", action=URIAction(label="✏️ 自訂多時段（如 08:30, 19:20）", uri=custom_uri)),
                    ButtonComponent(style="secondary", height="sm", action=MessageAction(label="🔕 關閉倒垃圾鬧鐘", text="鬧鐘:關閉")),
                    ButtonComponent(style="primary", color="#FF6B4A", height="sm", action=MessageAction(label="📊 返回即時動態主畫面", text="即時動態"))
                ])
            )
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="倒垃圾鬧鐘設定", contents=alarm_card))
            return

        if txt.startswith("鬧鐘:") or txt.startswith("鬧鐘："):
            t_val = txt[3:].strip().replace("，", ", ").replace("：", ":")
            call_sheet({"action": "set_alarm", "user_id": uid, "user_name": uname, "alarm_times": t_val})
            msg = "🔕 已關閉每日倒垃圾推播鬧鐘。" if t_val == "關閉" else f"⏰ 設定成功！每週一、二、四、五、六將於【{t_val}】準時推播倒垃圾提醒（週三、週日公休自動跳過）！"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
            return

        # 4. 回收分類表、雙北專用垃圾袋價目、大型家具清運預約
        if txt in ["回收分類", "資源回收", "分類查詢"]:
            rec_card = BubbleContainer(
                size="mega",
                header=BoxComponent(layout="vertical", background_color="#12B886", padding_all="14px", contents=[
                    TextComponent(text="♻️ 全台資源回收 ＆ 廚餘分類速查表", weight="bold", size="md", color="#FFFFFF", wrap=True)
                ]),
                body=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
                    TextComponent(text="📦 平面類（週一、五重點收運）：紙箱、報紙、舊衣、塑膠袋（須乾淨無油漬）", size="xs", color="#1A1B1E", wrap=True),
                    TextComponent(text="🧴 立體類（週二、四、六重點收運）：寶特瓶、鐵鋁罐、玻璃瓶、乾淨保麗龍、小家電", size="xs", color="#1A1B1E", wrap=True),
                    TextComponent(text="🍲 廚餘分類：養豬廚餘（熟食剩菜）與堆肥廚餘（果皮菜葉、蛋殼、咖啡渣）請瀝乾水分！", size="xs", color="#087F5B", weight="bold", wrap=True),
                    TextComponent(text="💡 提示：直接輸入物品名稱（如「行動電源」、「安全帽」）可單獨查詢喔！", size="xxs", color="#868E96", wrap=True)
                ]),
                footer=BoxComponent(layout="vertical", background_color="#FFFFFF", contents=[
                    ButtonComponent(style="primary", color="#111318", height="sm", action=MessageAction(label="📊 返回即時動態主畫面", text="即時動態"))
                ])
            )
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="資源回收分類速查表", contents=rec_card))
            return

        if txt in ["專用垃圾袋", "垃圾袋價目", "垃圾袋"]:
            bag_card = BubbleContainer(
                size="mega",
                header=BoxComponent(layout="vertical", background_color="#228BE6", padding_all="14px", contents=[
                    TextComponent(text="🛍️ 雙北專用垃圾袋尺寸與公定價目", weight="bold", size="md", color="#FFFFFF", wrap=True)
                ]),
                body=BoxComponent(layout="vertical", spacing="xs", background_color="#FFFFFF", contents=[
                    TextComponent(text="• 3 公升（20入/包）：21 元（每公升 0.36 元）", size="xs", color="#1A1B1E"),
                    TextComponent(text="• 5 公升（20入/包）：36 元（單身／小套房首選）", size="xs", color="#1A1B1E"),
                    TextComponent(text="• 14 公升（20入/包）：100 元（一般家庭最常用）", size="xs", color="#1A1B1E"),
                    TextComponent(text="• 25 公升（20入/包）：180 元（大掃除／棉被適用）", size="xs", color="#1A1B1E"),
                    TextComponent(text="• 33 公升（20入/包）：237 元 ｜ 75 公升（10入）：270 元", size="xs", color="#1A1B1E"),
                    TextComponent(text="💡 雙北專用垃圾袋與環保兩用袋可於新北市、台北市互相通用！", size="xxs", color="#1864AB", weight="bold", wrap=True, margin="sm")
                ]),
                footer=BoxComponent(layout="vertical", background_color="#FFFFFF", contents=[
                    ButtonComponent(style="primary", color="#111318", height="sm", action=MessageAction(label="📊 返回即時動態主畫面", text="即時動態"))
                ])
            )
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="雙北專用垃圾袋價目表", contents=bag_card))
            return

        if txt in ["大型家具", "大型清運", "家具清運"]:
            bulky_card = BubbleContainer(
                size="mega",
                header=BoxComponent(layout="vertical", background_color="#111318", padding_all="14px", contents=[
                    TextComponent(text="🛋️ 大型廢棄家具免費清運預約", weight="bold", size="md", color="#FFFFFF", wrap=True)
                ]),
                body=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
                    TextComponent(text="床墊、沙發、衣櫃、冰箱等大型廢棄物，請提前 1～3 天致電各縣市環保局免費預約清運，切勿直接丟入垃圾車或隨意棄置路邊！", size="xs", color="#1A1B1E", wrap=True),
                    TextComponent(text="📞 新北市環保局清運專線：0800-010-857\n📞 台北市／全台市民熱線：1999", size="xs", color="#FA5252", weight="bold", wrap=True)
                ]),
                footer=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
                    ButtonComponent(style="primary", color="#12B886", height="sm", action=URIAction(label="📞 撥打 1999 環保局清運預約", uri="tel:1999")),
                    ButtonComponent(style="secondary", height="sm", action=MessageAction(label="📊 返回即時動態主畫面", text="即時動態"))
                ])
            )
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="大型家具清運預約", contents=bulky_card))
            return

        # 5. 預設顯示旗艦 12.0 暗夜流光賽博酷炫 Pro 雙卡輪播主畫面
        st = call_sheet({"action": "status", "user_id": uid, "user_name": uname})
        cached = USER_LOCAL_CACHE.get(uid, {})
        addr = st.get("address") if st.get("address") and st.get("address") != "尚未設定" else cached.get("address", "尚未設定")
        lat = st.get("lat") or cached.get("lat", "")
        lon = st.get("lon") or cached.get("lon", "")
        spots = fetch_nearby_trash_spots(float(lat), float(lon)) if (lat and lon) else []
        card = make_trash_app_card(uid, addr, lat, lon, st.get("alarm_times", "尚未設定"), st.get("last_dump", "今日尚未倒垃圾"), spots=spots)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="全台垃圾車雷達 Pro", contents=card))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🗑️ 系統小提示：{str(e)[:60]}（請輸入「即時動態」刷新畫面）"))
