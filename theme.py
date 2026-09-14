"""主题与设计常量:颜色、字号、尺寸、动画时长全部集中于此,组件不得内联色值。

取值来源:design/横卡设计稿.html(定稿横卡,380x184)。
"""

# —— 画布 ——
CARD_W, CARD_H = 380, 184
RADIUS = 14
BORDER_W = 1

# —— 颜色 ——
C_CARD_BG = "#0f1115"          # 卡片底
C_CARD_BORDER = "#262a31"      # 卡片描边
C_DIVIDER = "#1f232a"          # 分隔线/占比条底
C_TEXT_BIG = "#f5f7fa"         # 今日大数字
C_TEXT_HEAD = "#e8eaed"        # 顶行标题
C_TEXT_LABEL = "#5f6672"       # 标签灰(输入/输出/缓存/今日TOKENS)
C_TEXT_DIM = "#6b7280"         # 次要灰(次数)
C_TEXT_VALUE = "#c9cfd8"       # 三列数值/模型名
C_TEXT_MODEL_VAL = "#f0f3f5"   # 模型数值
C_ACCENT = "#3ddc84"           # 强调绿:呼吸灯/飘字/第一模型
C_MODEL2 = "#39d0ff"           # 第二模型
C_MODEL3 = "#ffb454"           # 第三模型
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
