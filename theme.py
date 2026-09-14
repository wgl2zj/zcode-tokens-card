"""主题与设计常量:颜色、字号、尺寸、动画时长全部集中于此,组件不得内联色值。

皮肤:深色亚克力玻璃(玻璃拟态,选型稿 design/皮肤总览.html 04 号):
半透明渐变底 + 白色亮边 + 内缘反光高光;Win10 下由 main.py 叠加 DWM 亚克力模糊。
底色取深色系:悬浮窗常驻 ZCode 浅色界面之上,深玻璃保证白字始终可读。
窗体 356x192(用户指定,默认置于主屏右下、ZCode 窗口右下空白区)。
"""

# —— 画布 ——
CARD_W, CARD_H = 356, 192
RADIUS = 16
BORDER_W = 1

# —— 玻璃底与描边(半透明件:RGB 与 alpha 分开给) ——
C_GLASS_TOP = "#3b4459"        # 玻璃渐变起色(左上,亮蓝灰)
C_GLASS_BOTTOM = "#121724"     # 玻璃渐变止色(右下,近黑蓝)
A_GLASS_TOP = 0.60             # 玻璃底 alpha(上端)
A_GLASS_BOTTOM = 0.68          # 玻璃底 alpha(下端)
C_CARD_BORDER = "#ffffff"      # 卡片描边(白)
A_CARD_BORDER = 0.38           # 描边 alpha
A_EDGE_GLOW = 0.50             # 内缘高光顶部 alpha(玻璃上缘反光,向下渐隐)
C_DIVIDER = "#ffffff"          # 分隔线/占比条底(白)
A_DIVIDER = 0.22               # 分隔线/占比条底 alpha

# —— 颜色(文字为实色,取半透明白叠深玻璃的视觉等效值) ——
C_TEXT_BIG = "#ffffff"         # 今日大数字
C_TEXT_HEAD = "#eef2f9"        # 顶行标题
C_TEXT_LABEL = "#c2c9d8"       # 标签灰白(输入/输出/缓存/今日TOKENS)
C_TEXT_DIM = "#9aa3b7"         # 次要灰白(次数)
C_TEXT_VALUE = "#f0f4fb"       # 三列数值/模型名
C_TEXT_MODEL_VAL = "#ffffff"   # 模型数值
C_ACCENT = "#7df0cd"           # 强调薄荷绿:呼吸灯/飘字/第一模型
C_MODEL2 = "#82c8ff"           # 第二模型
C_MODEL3 = "#ffc46b"           # 第三模型(异常态呼吸灯)
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
