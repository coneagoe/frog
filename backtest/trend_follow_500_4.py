import os
import sys
import backtrader as bt
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf     # noqa: E402
from common import (
    enable_optimize,
    run,
    show_position,
)   # noqa: E402


conf.parse_config()


start_date = "20231101"
end_date = "20240513"

# 股票池
stocks = [
    '000009',
    '000021',
    '000027',
    '000031',
    '000039',
    '000050',
    '000060',
    '000066',
    '000089',
    '000155',
    '000156',
    '000400',
    '000401',
    '000402',
    '000423',
    '000513',
    '000519',
    '000537',
    '000539',
    '000547',
    '000553',
    # '000559',
    '000563',
    '000581',
    '000591',
    '000598',
    '000623',
    '000629',
    '000630',
    '000636',
    '000683',
    '000703',
    '000709',
    '000723',
    '000728',
    '000729',
    '000738',
    '000739',
    '000750',
    '000778',
    '000783',
    '000785',
    '000825',
    '000830',
    '000831',
    '000878',
    '000883',
    '000887',
    '000893',
    '000898',
    '000930',
    '000932',
    '000933',
    '000937',
    '000958',
    '000959',
    '000960',
    '000967',
    '000970',
    '000975',
    '000987',
    '000988',
    '000997',
    '000998',
    # '001203',
    '001227',
    '001286',
    '001872',
    '001914',
    '002008',
    '002010',
    '002019',
    '002025',
    '002028',
    '002030',
    '002032',
    '002044',
    '002056',
    '002064',
    '002065',
    '002078',
    '002080',
    '002092',
    '002120',
    '002128',
    '002131',
    '002138',
    '002152',
    '002153',
    '002155',
    '002156',
    '002185',
    '002192',
    '002195',
    '002203',
    '002223',
    '002240',
    '002244',
    '002262',
    '002266',
    '002268',
    '002273',
    '002281',
    '002294',
    '002299',
    '002326',
    '002340',
    '002353',
    '002368',
    '002372',
    '002373',
    '002384',
    '002385',
    '002399',
    '002407',
    '002408',
    '002409',
    '002414',
    '002422',
    '002423',
    '002429',
    '002430',
    '002432',
    '002439',
    '002444',
    '002463',
    '002465',
    '002468',
    '002472',
    '002487',
    '002497',
    '002500',
    '002505',
    '002506',
    '002507',
    '002508',
    '002511',
    '002517',
    '002518',
    '002531',
    '002532',
    '002557',
    '002558',
    '002563',
    '002568',
    '002572',
    '002595',
    '002600',
    '002607',
    '002608',
    '002624',
    '002625',
    '002653',
    '002670',
    '002673',
    '002683',
    '002690',
    '002738',
    '002739',
    '002756',
    '002761',
    '002791',
    '002797',
    '002831',
    '002850',
    '002865',
    '002867',
    '002925',
    '002926',
    '002936',
    '002939',
    '002945',
    '002958',
    '002966',
    '003022',
    '003031',
    '003035',
    '300001',
    '300003',
    '300009',
    '300012',
    '300017',
    '300024',
    '300026',
    '300037',
    '300058',
    '300070',
    '300073',
    '300088',
    '300114',
    '300118',
    '300136',
    '300144',
    '300146',
    '300207',
    '300212',
    '300244',
    '300251',
    '300253',
    '300257',
    '300285',
    '300296',
    '300357',
    '300363',
    '300373',
    '300383',
    '300390',
    '300394',
    '300395',
    '300418',
    '300438',
    '300474',
    '300487',
    '300502',
    '300529',
    '300558',
    '300568',
    '300595',
    '300601',
    '300604',
    '300676',
    '300677',
    '300682',
    '300699',
    '300724',
    '300748',
    '300776',
    '300850',
    '300861',
    '300866',
    '300888',
    '301029',
    '301236',
    '600004',
    '600008',
    '600021',
    '600022',
    '600032',
    '600038',
    '600056',
    '600060',
    '600062',
    '600066',
    '600079',
    '600095',
    '600096',
    '600109',
    '600118',
    '600126',
    '600129',
    '600131',
    '600141',
    '600143',
    '600153',
    '600155',
    '600157',
    '600160',
    '600161',
    '600166',
    '600167',
    '600170',
    '600177',
    '600208',
    '600258',
    '600271',
    '600282',
    '600298',
    '600299',
    '600315',
    '600316',
    '600325',
    '600329',
    '600339',
    '600348',
    '600350',
    '600352',
    '600369',
    '600373',
    '600377',
    '600378',
    '600380',
    '600390',
    '600392',
    '600398',
    '600399',
    '600415',
    '600416',
    '600418',
    '600435',
    '600481',
    '600482',
    '600486',
    '600497',
    '600498',
    '600499',
    '600500',
    '600511',
    '600516',
    '600517',
    '600521',
    '600528',
    '600529',
    '600535',
    '600536',
    '600546',
    '600549',
    '600563',
    '600566',
    '600580',
    '600582',
    '600583',
    '600597',
    '600598',
    '600637',
    '600642',
    '600655',
    '600663',
    '600673',
    '600699',
    '600704',
    '600707',
    '600737',
    '600739',
    '600755',
    '600764',
    '600765',
    '600801',
    '600808',
    '600820',
    '600827',
    '600839',
    '600848',
    '600859',
    '600862',
    '600863',
    '600867',
    '600871',
    '600873',
    '600879',
    '600884',
    '600885',
    '600895',
    '600901',
    '600906',
    '600909',
    '600925',
    '600927',
    '600928',
    '600956',
    '600959',
    '600967',
    '600968',
    '600970',
    '600977',
    '600985',
    '600988',
    '600995',
    '600998',
    '601000',
    '601016',
    '601058',
    '601061',
    '601077',
    '601098',
    '601106',
    '601108',
    '601118',
    '601128',
    '601139',
    '601156',
    '601158',
    '601162',
    '601168',
    '601179',
    '601187',
    '601198',
    '601216',
    '601228',
    '601231',
    '601233',
    '601298',
    # '601456',
    '601555',
    '601568',
    '601577',
    '601598',
    '601608',
    '601611',
    '601636',
    '601665',
    '601666',
    '601696',
    '601717',
    '601778',
    '601828',
    '601866',
    '601880',
    '601928',
    '601933',
    '601958',
    '601966',
    '601990',
    '601991',
    '601992',
    '601997',
    '603000',
    '603026',
    '603056',
    '603077',
    '603127',
    '603156',
    '603160',
    '603185',
    '603218',
    '603225',
    '603228',
    '603233',
    '603267',
    '603305',
    '603317',
    '603338',
    '603355',
    '603379',
    '603444',
    '603456',
    '603517',
    '603529',
    '603568',
    '603589',
    '603596',
    '603606',
    '603650',
    '603658',
    '603688',
    '603707',
    '603712',
    '603737',
    '603786',
    '603816',
    '603826',
    '603858',
    '603866',
    '603868',
    '603882',
    '603883',
    '603885',
    '603893',
    '603927',
    '603939',
    '605358',
    '688002',
    '688005',
    '688006',
    '688029',
    '688032',
    '688052',
    '688063',
    '688072',
    '688082',
    '688099',
    '688105',
    '688107',
    '688114',
    '688120',
    '688122',
    '688153',
    '688169',
    '688180',
    '688188',
    '688200',
    '688208',
    '688220',
    '688234',
    '688248',
    '688276',
    '688281',
    '688295',
    '688297',
    '688301',
    '688331',
    '688348',
    '688349',
    '688375',
    '688385',
    '688387',
    '688390',
    '688425',
    '688516',
    '688520',
    '688521',
    '688536',
    '688538',
    '688567',
    '688690',
    '688728',
    '688772',
    '688778',
    '688779',
    '688819',
    '689009',
]


class Context:
    def __init__(self):
        self.order = None
        self.open_price = None
        self.stop_price = None
        self.is_candidator = False

    def reset(self):
        self.order = None
        self.open_price = None
        self.stop_price = None
        self.is_candidator = False


gContext = [Context() for i in range(len(stocks))]


# enable_optimize()


class TrendFollowingStrategy(bt.Strategy):
    params = (
            ('ema_period', 20),
            ('num_positions', 30),       # 最大持仓股票数
            # ('num_positions', 2),       # 最大持仓股票数
            ('p_macd_1_dif', 6),
            ('p_macd_1_dea', 12),
            ('p_macd_1_signal', 5),
            ('p_macd_2_dif', 6),
            ('p_macd_2_dea', 12),
            ('p_macd_2_signal', 5),
        )


    def __init__(self):
        self.target = round(1 / (self.params.num_positions), 2)
        # self.target = round(1 / len(stocks), 2)

        self.ema20 = {i: bt.indicators.EMA(self.datas[i].close, period=20)
                      for i in range(len(self.datas))}

        self.ema15 = {i: bt.indicators.EMA(self.datas[i].close, period=15)
                      for i in range(len(self.datas))}

        self.ema10 = {i: bt.indicators.EMA(self.datas[i].close, period=10)
                      for i in range(len(self.datas))}

        self.ema5 = {i: bt.indicators.EMA(self.datas[i].close, period=5)
                      for i in range(len(self.datas))}

        self.macd_1 = {i: bt.indicators.MACD(self.datas[i].close,
                                             period_me1=self.params.p_macd_1_dif,
                                             period_me2=self.params.p_macd_1_dea,
                                             period_signal=self.params.p_macd_1_signal)
                                             for i in range(len(self.datas))}

        self.cross_signal_1 = {i: bt.indicators.CrossOver(self.macd_1[i].macd,
                                                        self.macd_1[i].signal)
                                                        for i in range(len(self.datas))}

        # self.middle = {i: (self.datas[i].high + self.datas[i].low) / 2.0
        #                                             for i in range(len(self.datas))}

        # self.macd_2 = {i: bt.indicators.MACD(self.middle[i],
        #                                      period_me1=self.params.p_macd_2_dif,
        #                                      period_me2=self.params.p_macd_2_dea,
        #                                      period_signal=self.params.p_macd_2_signal)
        #                                      for i in range(len(self.datas))}

        # self.cross_signal_2 = {i: bt.indicators.CrossOver(self.macd_2[i].macd,
        #                                                 self.macd_2[i].signal)
        #                                                 for i in range(len(self.datas))}


    def next(self):
        # 遍历所有的股票
        for i in range(len(self.datas)):
            if gContext[i].order is None:
                if gContext[i].is_candidator is False:
                    # 如果MACD金叉
                    if self.cross_signal_1[i] > 0:
                        gContext[i].is_candidator = True
                        continue
                else:
                    # 如果MACD死叉或MACD.macd曲线不光滑
                    if self.cross_signal_1[i] < 0 or self.macd_1[i].macd[0] - self.macd_1[i].macd[-1] <= 0:
                        gContext[i].is_candidator = False
                        continue
                    else:
                        if self.datas[i].close[0] > self.ema20[i][0] \
                            and self.macd_1[i].signal[0] > 0 and self.macd_1[i].macd[0] > 0:
                            self.order_target_percent(self.datas[i], target=self.target)
            else:
                # 计算当前收益率
                # print(f"foo: {i}, price: {self.datas[i].close[0]}, open_price: {gContext[i].open_price}")
                open_price = gContext[i].open_price
                profit_rate = round((self.datas[i].close[0] - open_price) / open_price, 4)
                if profit_rate < 0.2:
                    ema = self.ema20
                elif profit_rate < 0.4:
                    ema = self.ema15
                elif profit_rate < 0.6:
                    ema = self.ema10
                else:
                    ema = self.ema5

                if gContext[i].stop_price < ema[i][-1]:
                    gContext[i].stop_price = ema[i][-1]

                if self.datas[i].close[0] < gContext[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)
                    # gContext[i].reset()


    def notify_trade(self, trade):
        i = stocks.index(trade.getdataname())
        if trade.isopen:
            # print(f"foo: {trade.getdataname()}, price: {trade.price}, index: {i}")
            gContext[i].order = True
            gContext[i].open_price = trade.price
            gContext[i].stop_price = self.ema20[i][-1]
            gContext[i].is_candidator = False
            return

        if trade.isclosed:
            gContext[i].reset()

        # print('\n---------------------------- TRADE ---------------------------------')
        # print('Size: ', trade.size)
        # print('Price: ', trade.price)
        # print('Value: ', trade.value)
        # print('Commission: ', trade.commission)
        # print('Profit, Gross: ', trade.pnl, ', Net: ', trade.pnlcomm)
        # print('--------------------------------------------------------------------\n')


    def stop(self):
        print('(ema_period %d, num_positions %d) Ending Value %.2f' %
              (self.params.ema_period, self.params.num_positions, self.broker.getvalue()))

        show_position(self.positions)


cerebro = bt.Cerebro()

if os.environ.get('OPTIMIZER') == 'True':
    strats = cerebro.optstrategy(TrendFollowingStrategy,
                                 # ema_period=range(5, 30))
                                 num_positions=range(1, len(stocks)))
else:
    cerebro.addstrategy(TrendFollowingStrategy)

results = run(cerebro, stocks, start_date, end_date)
