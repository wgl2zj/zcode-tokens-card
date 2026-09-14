"""主题与设计常量:颜色、字号、尺寸、动画时长全部集中于此,组件不得内联色值。

皮肤:纸感浅色(选型稿 design/皮肤总览.html 01 号,用户选定):
暖白纸底 + 细灰线 + 少量橙强调,Notion 式文档安静气质,白天不刺眼。
窗体 356x192(用户指定,默认置于主屏右下、ZCode 窗口右下空白区)。
"""

# —— 画布 ——
CARD_W, CARD_H = 356, 192      # 卡片内容尺寸(视觉边界)
SHADOW_PAD = 14                # 窗口四周透明边距:容纳落地投影的绘制空间
WIN_W, WIN_H = CARD_W + SHADOW_PAD * 2, CARD_H + SHADOW_PAD * 2
RADIUS = 10
BORDER_W = 1

# —— 投影 ——
C_SHADOW = "#37352f"           # 投影色(暖灰黑,随卡片主文字色)
A_SHADOW_MAX = 0.047           # 贴卡处 alpha,向外逐层递减(贴近设计稿 5% 柔影)

# —— 颜色(纸感全实色,无需半透明件) ——
C_CARD_BG = "#fdfcf9"          # 卡片底(暖白纸)
C_CARD_BORDER = "#e9e5dc"      # 卡片描边(细灰线)
C_DIVIDER = "#eeece5"          # 分隔线/占比条底
C_TEXT_BIG = "#37352f"         # 今日大数字
C_TEXT_HEAD = "#5f5e5b"        # 顶行标题
C_TEXT_LABEL = "#a39d90"       # 标签灰(输入/输出/缓存/今日TOKENS)
C_TEXT_DIM = "#a39d90"         # 次要灰(次数)
C_TEXT_VALUE = "#37352f"       # 三列数值/模型名
C_TEXT_MODEL_VAL = "#37352f"   # 模型数值
C_ERROR = "#d4442e"            # 异常态:呼吸灯与状态文字(红橙)
C_ACCENT = "#d9730d"           # 强调橙:呼吸灯/飘字/第一模型
C_MODEL2 = "#0f7b6c"           # 第二模型(青绿)
C_MODEL3 = "#2383e2"           # 第三模型(蓝)
MODEL_COLORS = (C_ACCENT, C_MODEL2, C_MODEL3)

# —— 字号(px) ——
FS_BIG = 33          # 今日大数字
FS_INC = 14          # 大数字飘字
FS_HEAD = 12.5       # 顶行"今日 · …"
FS_REQ = 11          # 顶行"…次"
FS_CAP = 10.5        # "今日 TOKENS"
FS_MI_K = 10.5       # 三列标签
FS_MI_V = 12.5       # 三列数值
FS_INC2 = 10         # 右栏飘字
FS_MNAME = 12.5      # 模型名
FS_MVAL = 14.5       # 模型数值

# —— 字体族 ——
F_MONO = "Consolas"           # 数字/代码感文本
F_UI = "Microsoft YaHei"      # 中文界面文本

# —— 动画(ms) ——
POLL_MS = 1500                # 数据轮询间隔
TWEEN_MS = 800                # 数值补间
INC_RISE_MS = 1400            # 大数字飘字生命周期
INC2_RISE_MS = 1200           # 右栏飘字生命周期
BAR_MS = 900                  # 占比条过渡
BREATH_MS = 2400              # 呼吸灯周期
FRAME_MS = 33                 # 重绘帧间隔(~30fps)

# —— 数据源 ——
DB_PATH = None                # 由 reader 模块按用户主目录解析,此处不留路径常量
