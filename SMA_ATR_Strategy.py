import pandas as pd # 导入 pandas，虽然这里直接用 backtrader 的 feed，但保持导入是个好习惯
import backtrader as bt 
import matplotlib.pyplot as plt # 导入 matplotlib 的 pyplot 模块

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

print(f"数据文件 '{data_file}' 已成功加载到 backtrader 引擎中。")
print("接下来，我们将定义我们的双均线策略！")
class DualMovingAverage(bt.Strategy):
    # 定义策略的参数
    params = (('fast_length', 25),
              ('slow_length', 200),
              ('atr_period', 14),   # ATR周期
              ('atr_multiple', 2.0) # ATR的倍数，用于计算止损距离
             )
    
    def __init__(self):
        # 记录收盘价，方便后续使用
        self.dataclose = self.datas[0].close
        # 用来跟踪未完成的订单
        self.order = None
        self.buyprice = None
        self.comm = None
        self.stop_price = None
        # 均线指标
        self.fast_ma = bt.indicators.SMA(self.dataclose, period=self.p.fast_length)
        self.slow_ma = bt.indicators.SMA(self.dataclose, period=self.p.slow_length)
        # ATR指标
        self.atr = bt.indicators.ATR(self.datas[0], period=self.p.atr_period)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buyprice = order.executed.price
                self.comm = order.executed.comm
                # 买入后立即设置初始止损价
                self.stop_price = self.buyprice - (self.atr[0]) * self.p.atr_multiple
                print(f"买入执行 - 日期: {self.data.datetime.date()}, 价格: {order.executed.price:.2f}, "
                      f"初始止损价: {self.stop_price:.2f}, 佣金: {order.executed.comm:.2f}")
            elif order.issell():
                print(f"卖出执行 - 日期: {self.data.datetime.date()}, 价格: {order.executed.price:.2f}, "
                      f"佣金: {order.executed.comm:.2f}")
            self.bar_executed = len(self) # 记录订单执行时的 bar 数量
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"订单状态: {order.Status[order.status]} - 日期: {self.data.datetime.date()}")
        self.order = None

    def notify_trade(self, trade):
        # 交易完成（平仓）时调用
        if not trade.isclosed:
            return
        print(f"交易完成 - 毛利润: {trade.pnl:.2f}, 净利润: {trade.pnlcomm:.2f}")
        
    def next(self):
        max_period = max(self.p.atr_period, self.p.slow_length, self.p.fast_length)
        if len(self) < max(self.p.fast_length, self.p.slow_length):
            return

        if self.order:
            return

        # 获取今天的收盘价和 ATR 值
        current_close = self.dataclose[0]
        current_atr = self.atr[0]

        # --- 卖出逻辑 (止损优先) ---
        if self.position: # 如果持有仓位
            # 1. 检查是否达到止损价
            if self.stop_price is not None and current_close < self.stop_price:
                print(f"止损触发！日期: {self.data.datetime.date()}, "
                      f"当前收盘: {current_close:.2f}, 止损价: {self.stop_price:.2f}")
                self.close() # 平仓
                self.stop_price = None # 止损后清空止损价
                return # 止损触发，本周期不再检查其他条件
            # 2. 如果没有止损，或者止损价可以上移，更新止损价
            # 新的止损价 = 当前收盘价 - (ATR * ATR_multiple)
            new_stop_price = current_close - (current_atr * self.p.atr_multiple)
            if self.stop_price is None or new_stop_price > self.stop_price:
                self.stop_price = new_stop_price
                # 可以选择打印止损价更新信息，但通常过于频繁
                # print(f"止损价更新 - 日期: {self.data.datetime.date()}, 新止损价: {self.stop_price:.2f}")
            # 3. 均线死叉平仓 (如果止损没触发，再检查均线)
            if self.fast_ma[0] < self.slow_ma[0] and self.fast_ma[-1] > self.slow_ma[-1]:
                print(f"均线死叉平仓 - 日期: {self.data.datetime.date()}, "
                      f"快线: {self.fast_ma[0]:.2f}, 慢线: {self.slow_ma[0]:.2f}")
                self.close()
                self.stop_price = None # 平仓后清空止损价
        # --- 买入逻辑 ---
        else: # 没有持仓
            if self.fast_ma[0] > self.slow_ma[0] and self.fast_ma[-1] < self.slow_ma[-1]:
                self.order = self.buy(size=10)
                print(f"发出买入信号 - 日期: {self.data.datetime.date()}, 快速均线: {self.fast_ma[0]:.2f}, 慢速均线: {self.slow_ma[0]:.2f}")

if __name__ == '__main__':
    # 创建一个 Cerebro 引擎（回测的大脑）
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_analyzer")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns_analyzer", timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_ratio", timeframe=bt.TimeFrame.Years) # 添加夏普比率
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Days # 明确指定数据的时间框架是日线
    )

    # 将数据 Feed 添加到 Cerebro 引擎
    cerebro.adddata(data)
    # 添加策略到 Cerebro 引擎
    cerebro.addstrategy(DualMovingAverage)
    # 设置初始资金
    cerebro.broker.setcash(100000.0) # 初始资金 100,000
    # 设置佣金 (这里设置为万分之一，可以根据实际情况调整)
    cerebro.broker.setcommission(commission=0.0001)
    # 打印初始资金
    print(f"初始资金: {cerebro.broker.getvalue():.2f}")

    # 运行回测
    results = cerebro.run()  # 建议将变量名改为复数形式，以提醒自己它是一个列表
    thestrat = results[0]    # 获取列表中的第一个策略实例
    # 通过策略实例访问分析器
    trade_analyzer = thestrat.analyzers.trade_analyzer.get_analysis()
    returns_analyzer = thestrat.analyzers.returns_analyzer.get_analysis()
    sharpe_ratio = thestrat.analyzers.sharpe_ratio.get_analysis()

    # 打印最终资金
    print(f"最终资金: {cerebro.broker.getvalue():.2f}")
    # 打印分析结果
    if trade_analyzer.total.closed > 0:
        print(f"总收益率: {returns_analyzer.get('rtot', 0) * 100:.2f}%")
        print(f"总交易次数: {trade_analyzer.total.closed}")
    else:
        print("没有发生任何交易。")

    # 夏普比率可能为 None，需要检查
    sharpe_ratio_value = sharpe_ratio.get('sharperatio')
    if sharpe_ratio_value is not None:
        print(f"夏普比率: {sharpe_ratio_value:.4f}")
    else:
        print("夏普比率: N/A")

    # 绘制图表
    cerebro.plot()
