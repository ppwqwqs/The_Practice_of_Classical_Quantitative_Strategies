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

# print(f"数据文件 '{data_file}' 已成功加载到 backtrader 引擎中。")
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
# -----------------------------------------------------------
# 将策略添加到 Cerebro 引擎并运行回测
# -----------------------------------------------------------
if __name__ == "__main__":
    # 创建一个 Cerebro 引擎（回测的大脑）
    cerebro = bt.Cerebro()

    # 创建数据 Feed
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Days
    )

    # 将数据 Feed 添加到 Cerebro 引擎
    cerebro.adddata(data)
    # 设置初始资金
    initial_cash = 100000.0
    cerebro.broker.setcash(initial_cash)
    # 设置佣金 (这里设置为万分之一，可以根据实际情况调整)
    cerebro.broker.setcommission(commission=0.0001)
    # ************************************************************
    # 核心优化部分：定义参数范围
    # ************************************************************
    cerebro.optstrategy(
        DualMovingAverage, # 我们要优化的策略类
        fast_length=range(10, 31, 5), # fast_length 从 10 到 30，步长为 5 (10, 15, 20, 25, 30)
        slow_length=range(50, 200, 10) # slow_length 从 50 到 100，步长为 10 (50, 60, 70, 80, 90, 100)
    )
    # ************************************************************
    # 添加分析器来收集回测结果
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_analyzer")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns_analyzer", timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_ratio", timeframe=bt.TimeFrame.Years) # 添加夏普比率
    # 打印提示
    print("开始运行参数优化回测...")
    # 运行优化回测
    results = cerebro.run()
    print("参数优化回测完成！")
    print("\n开始分析优化结果...")
    # -----------------------------------------------------------
    # 分析和打印优化结果
    # -----------------------------------------------------------
    best_strategy = None
    best_returns = -float('inf') # 初始化为负无穷，用于找到最大收益
    print("\n--- 优化结果汇总 ---")
    for stratrun in results: # 遍历每次策略运行
        for s in stratrun: # 遍历每次运行中的策略实例 (通常只有一个)
            # 获取策略的参数
            p = s.p
            # 获取分析器的结果
            trade_analyzer = s.analyzers.trade_analyzer.get_analysis()
            returns_analyzer = s.analyzers.returns_analyzer.get_analysis()
            sharpe_ratio = s.analyzers.sharpe_ratio.get_analysis()
            # 获取总收益率 (Total Returns)
            # returns_analyzer.rtot 是总收益率，已经考虑了资金变动
            total_returns_percentage = returns_analyzer['rtot'] * 100 if 'rtot' in returns_analyzer else 0.0
            # 最终资金可以通过初始资金 + 初始资金 * 总收益率 计算
            final_value = initial_cash * (1 + total_returns_percentage / 100)
            # 打印当前参数组合的结果
            print(f"  fast_length: {p.fast_length}, slow_length: {p.slow_length}")
            print(f"    最终资金: {final_value:.2f}")
            print(f"    总收益率: {total_returns_percentage:.2f}%")
            # 确保 trade_analyzer 有效数据再访问
            total_closed_trades = trade_analyzer.total.closed if 'total' in trade_analyzer and 'closed' in trade_analyzer.total else 0
            print(f"    交易总数: {total_closed_trades}")
            if sharpe_ratio and sharpe_ratio.get('sharperatio') is not None:
                print(f"    夏普比率: {sharpe_ratio['sharperatio']:.4f}") # 使用字典访问
            else:
                print("    夏普比率: N/A (可能数据不足或波动为0)")
            # 记录最佳参数
            if total_returns_percentage > best_returns:
                best_returns = total_returns_percentage
                best_strategy = {
                    'fast_length': p.fast_length,
                    'slow_length': p.slow_length,
                    'returns': total_returns_percentage,
                    'final_value': final_value,
                    'total_trades': total_closed_trades,
                    'sharpe_ratio': sharpe_ratio['sharperatio'] if sharpe_ratio and sharpe_ratio.get('sharperatio') is not None else 'N/A'
                }
    if best_strategy:
        print("\n--- 最佳参数组合 ---")
        print(f"  快速均线周期 (Fast MA Length): {best_strategy['fast_length']}")
        print(f"  慢速均线周期 (Slow MA Length): {best_strategy['slow_length']}")
        print(f"  最终资金 (基于优化): {best_strategy['final_value']:.2f}")
        print(f"  最高收益率 (基于优化): {best_strategy['returns']:.2f}%")
        print(f"  交易总数 (基于优化): {best_strategy['total_trades']}")
        print(f"  夏普比率 (基于优化): {best_strategy['sharpe_ratio']:.4f}" if best_strategy['sharpe_ratio'] != 'N/A' else f"  夏普比率: {best_strategy['sharpe_ratio']}")
        print("\n--- 重新运行最佳策略进行验证 ---")
        cerebro_best = bt.Cerebro()
        cerebro_best.adddata(data) # 确保数据再次被添加
        # 设置相同的初始资金和佣金
        cerebro_best.broker.setcash(initial_cash) # 使用之前定义的 initial_cash
        cerebro_best.broker.setcommission(commission=0.0001)
        # 添加最佳策略
        cerebro_best.addstrategy(DualMovingAverage,
                                fast_length=best_strategy['fast_length'],
                                slow_length=best_strategy['slow_length'],
                                )
        # ************************************************************
        # 关键：在重新运行最佳策略时，也添加相同的分析器
        # ************************************************************
        cerebro_best.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_analyzer_best")
        cerebro_best.addanalyzer(bt.analyzers.Returns, _name="returns_analyzer_best", timeframe=bt.TimeFrame.Days)
        cerebro_best.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_ratio_best", timeframe=bt.TimeFrame.Years)
        print(f"初始资金: {cerebro_best.broker.getvalue():.2f}")
        best_results = cerebro_best.run() # 运行最佳策略的回测
        # 获取最佳策略运行的分析结果
        best_s = best_results[0] # 优化运行返回的是列表的列表，单次回测也是如此，所以取第一个
        trade_analyzer_best = best_s.analyzers.trade_analyzer_best.get_analysis()
        returns_analyzer_best = best_s.analyzers.returns_analyzer_best.get_analysis()
        sharpe_ratio_best = best_s.analyzers.sharpe_ratio_best.get_analysis()
        # 计算并打印结果
        final_value_best = cerebro_best.broker.getvalue() # 直接获取最终资金
        total_returns_percentage_best = returns_analyzer_best['rtot'] * 100 if 'rtot' in returns_analyzer_best else 0.0
        total_closed_trades_best = trade_analyzer_best.total.closed if 'total' in trade_analyzer_best and 'closed' in trade_analyzer_best.total else 0
        sharpe_value_best = sharpe_ratio_best['sharperatio'] if sharpe_ratio_best and sharpe_ratio_best.get('sharperatio') is not None else 'N/A'
        print(f"重新运行最终资金: {final_value_best:.2f}")
        print(f"重新运行总收益率: {total_returns_percentage_best:.2f}%")
        print(f"重新运行交易总数: {total_closed_trades_best}")
        print(f"重新运行夏普比率: {sharpe_value_best:.4f}" if sharpe_value_best != 'N/A' else f"重新运行夏普比率: {sharpe_value_best}")
        cerebro_best.plot()
    else:
        print("\n没有找到有效的优化结果，无法重新运行最佳策略。")