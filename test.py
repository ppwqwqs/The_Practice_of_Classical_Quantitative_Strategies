import pandas as pd # 导入 pandas，虽然这里直接用 backtrader 的 feed，但保持导入是个好习惯
import backtrader as bt 
import matplotlib.pyplot as plt # 导入 matplotlib 的 pyplot 模块
# %matplotlib inline
# 定义下载的文件
data_file = "GC=F_historical_data.csv"
column_names = ['Date', 'Close', 'High', 'Low', 'Open', 'Volume']

# 使用 pandas 读取 CSV 文件，跳过前三行 (header=3)，并且手动指定列名
df = pd.read_csv(
    data_file,
    header=None,
    skiprows=3,
    names=column_names, # 手动指定列名
    index_col=0,   # 将第一列（日期）设置为索引
    parse_dates=True # 将索引列解析为日期时间对象
)

if 'Adj Close' not in df.columns:
    df['Adj Close'] = df['Close']

# 我们需要重新排列一下 df 的列
df = df[['Open', 'High', 'Low', 'Close', 'Volume', 'Adj Close']]
# 打印数据的前几行和列信息，方便调试
print("Pandas DataFrame 前几行：")
print(df.head())
print("\nPandas DataFrame 列信息：")
print(df.info())

# 创建一个 Cerebro 引擎（回测的大脑）
cerebro = bt.Cerebro()

# 创建数据 Feed
# 我们使用 GenericCSVData，因为 yfinance 导出的 CSV 文件列名是标准的
# 将 Pandas DataFrame 传递给 backtrader
data = bt.feeds.PandasData(
    dataname=df,
    # fromdate=datetime.datetime(2020, 1, 2), # 使用 datetime 模块指定日期
    # todate=datetime.datetime(2025, 12, 31),
    timeframe=bt.TimeFrame.Days # 明确指定数据的时间框架是日线
)

# 将数据 Feed 添加到 Cerebro 引擎
cerebro.adddata(data)

print(f"数据文件 '{data_file}' 已成功加载到 backtrader 引擎中。")
print("接下来，我们将定义我们的双均线策略！")

class DualMovingAverage(bt.Strategy):
    # 定义策略的参数
    params = (('fast_length', 20), # 快速移动平均线周期
              ('slow_length', 60), # 慢速移动平均线周期
             )
    
    def __init__(self):
        # 记录收盘价，方便后续使用
        self.dataclose = self.datas[0].close
        # 用来跟踪未完成的订单
        self.order = None
        self.buyprice = None # 记录买入价格
        self.comm = None     # 记录佣金
        # 创建两条移动平均线指标
        self.fast_ma = bt.indicators.SMA(self.dataclose, period=self.p.fast_length)
        self.slow_ma = bt.indicators.SMA(self.dataclose, period=self.p.slow_length)
        # 我们将不再使用 bt.indicators.CrossOver 指标，直接在 next 方法中判断交叉
        
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # 订单已提交/接受，等待执行
            return
        # 如果订单是完成状态 (买入/卖出)
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buyprice = order.executed.price
                self.comm = order.executed.comm
                print(f"买入执行 - 日期: {self.data.datetime.date()}, 价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 佣金: {order.executed.comm:.2f}")
            elif order.issell():
                print(f"卖出执行 - 日期: {self.data.datetime.date()}, 价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 佣金: {order.executed.comm:.2f}")
            self.bar_executed = len(self) # 记录订单执行时的 bar 数量
        # 如果订单是取消、保证金不足、拒绝等状态
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"订单状态: {order.Status[order.status]} - 日期: {self.data.datetime.date()}")
        # 重置订单跟踪，表示没有未完成的订单了
        self.order = None

    def notify_trade(self, trade):
        # 交易完成（平仓）时调用
        if not trade.isclosed:
            return
        print(f"交易完成 - 毛利润: {trade.pnl:.2f}, 净利润: {trade.pnlcomm:.2f}")
        
    def next(self):
        # 确保两条均线都有足够的数据点来计算
        # SMA 需要至少 period 数量的数据点才能计算出第一个值
        if len(self) < max(self.p.fast_length, self.p.slow_length):
            return # 数据不足，跳过
        # 如果有未完成的订单，则不进行新的操作
        if self.order:
            return
        # 检查是否持有仓位 (即当前是否持有股票/期货)
        if not self.position: # 没有持仓
            # 判断金叉信号：快速均线向上穿过慢速均线
            # 当前快速均线 > 当前慢速均线 AND 上一周期快速均线 < 上一周期慢速均线
            if self.fast_ma[0] > self.slow_ma[0] and self.fast_ma[-1] < self.slow_ma[-1]:
                # 买入
                self.order = self.buy(size=10) # 假设买入10个单位
                print(f"发出买入信号 - 日期: {self.data.datetime.date()}, 快速均线: {self.fast_ma[0]:.2f}, 慢速均线: {self.slow_ma[0]:.2f}")
        else: # 持有仓位 (做多)
            # 判断死叉信号：快速均线向下穿过慢速均线
            # 当前快速均线 < 当前慢速均线 AND 上一周期快速均线 > 上一周期慢速均线
            if self.fast_ma[0] < self.slow_ma[0] and self.fast_ma[-1] > self.slow_ma[-1]:
                # 卖出（平仓）
                self.order = self.close() # 平仓所有持仓
                print(f"发出卖出信号 - 日期: {self.data.datetime.date()}, 快速均线: {self.fast_ma[0]:.2f}, 慢速均线: {self.slow_ma[0]:.2f}")

# 添加策略到 Cerebro 引擎
cerebro.addstrategy(DualMovingAverage)
# 设置初始资金
cerebro.broker.setcash(100000.0) # 初始资金 100,000
# 设置佣金 (这里设置为万分之一，可以根据实际情况调整)
cerebro.broker.setcommission(commission=0.0001)
# 打印初始资金
print(f"初始资金: {cerebro.broker.getvalue():.2f}")
# 运行回测
cerebro.run()
# 打印最终资金
print(f"最终资金: {cerebro.broker.getvalue():.2f}")

cerebro.plot(iplot=False)