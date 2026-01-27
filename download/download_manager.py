import logging
from datetime import datetime
from typing import Any, Callable

import pandas as pd
import pandas_market_calendars as mcal

from common.const import COL_DATE, COL_STOCK_ID, AdjustType, PeriodType, SecurityType
from storage import (
    get_storage,
    get_table_name,
    tb_name_general_info_stock,
    tb_name_ingredient_300,
    tb_name_ingredient_500,
)
from storage.model import (
    tb_name_a_stock_basic,
    tb_name_daily_basic_a_stock,
    tb_name_stk_limit_a_stock,
    tb_name_suspend_d_a_stock,
)

from .dl import Downloader
from .mp_utils import run_history_download_mp


class DownloadManager:
    def __init__(self):
        self.downloader = Downloader()

    def download_general_info_stock(self) -> bool:
        get_storage().drop_table(tb_name_general_info_stock)

        df = self.downloader.dl_general_info_stock()
        if df is None or df.empty:
            logging.warning("Failed to download stock info or data is empty.")
            return False

        return get_storage().save_general_info_stock(df)

    def download_general_info_etf(self) -> bool:
        df = self.downloader.dl_general_info_etf()
        if df is None or df.empty:
            logging.warning("Failed to download ETF info or data is empty.")
            return False

        return get_storage().save_general_info_etf(df)

    def download_general_info_hk_ggt(self) -> bool:
        df = self.downloader.dl_general_info_hk_ggt_stock()
        if df is None or df.empty:
            logging.warning("Failed to download HK GGT info or data is empty.")
            return False

        return get_storage().save_general_info_hk_ggt(df)

    def _download_history_data(
        self,
        table_name: str,
        security_id: str,
        period: PeriodType,
        start_date: str,
        end_date: str,
        adjust: AdjustType,
        downloader_func: Callable[[str, str, str, PeriodType, AdjustType], Any],
        storage_save_func: Callable[[Any, PeriodType, AdjustType], bool],
    ) -> bool:
        try:
            last_record = get_storage().get_last_record(table_name, security_id)

            if last_record is not None:
                latest_date = pd.Timestamp(last_record[COL_DATE])
                actual_start_ts = latest_date + pd.Timedelta(days=1)
                actual_start_date = actual_start_ts.strftime("%Y%m%d")

                if actual_start_ts > pd.to_datetime(end_date):
                    logging.info(f"Data for {security_id} is already up to date")
                    return True
            else:
                actual_start_date = start_date

            df = downloader_func(
                security_id, actual_start_date, end_date, period, adjust
            )

            if df is None or df.empty:
                logging.info(f"No new data for {security_id}")
                return True

            return storage_save_func(df, period, adjust)

        except Exception as e:
            logging.error(f"Error processing history for {security_id}: {e}")
            return False

    def download_stock_history(
        self,
        stock_id: str,
        period: PeriodType,
        start_date: str,
        end_date: str,
        adjust: AdjustType = AdjustType.QFQ,
    ) -> bool:
        table_name = get_table_name(SecurityType.STOCK, period, adjust)

        return self._download_history_data(
            table_name=table_name,
            security_id=stock_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            downloader_func=self.downloader.dl_history_data_stock,
            storage_save_func=get_storage().save_history_data_stock,
        )

    def download_all_stock_history(
        self,
        period: PeriodType = PeriodType.DAILY,
        adjust: AdjustType = AdjustType.QFQ,
        start_date: str = "2000-01-01",
        end_date: str = None,
    ) -> bool:
        """
        下载所有股票的历史数据

        Args:
            period: 周期类型（日/周/月）
            adjust: 复权类型（前复权/后复权）
            start_date: 开始日期，默认为2000-01-01
            end_date: 结束日期，默认为当天

        Returns:
            bool: 是否成功完成所有股票的下载
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        logging.info(
            f"开始下载所有股票历史数据，周期: {period.value}, 复权: {adjust.value}, 日期范围: {start_date} 到 {end_date}"
        )

        table_name = get_table_name(SecurityType.STOCK, period, adjust)

        try:
            if adjust == AdjustType.QFQ:
                get_storage().drop_table(table_name)

            df_stocks = get_storage().load_general_info_stock()

            if df_stocks is None or df_stocks.empty:
                logging.error("无法获取股票基本信息数据")
                return False

            stock_ids = df_stocks[COL_STOCK_ID].tolist()
            total_stocks = len(stock_ids)

            logging.info(f"共获取到 {total_stocks} 只股票，开始多进程下载历史数据...")

            result = run_history_download_mp(
                security_type=SecurityType.STOCK,
                ids=stock_ids,
                period_value=period.value,
                adjust_value=adjust.value,
                start_date=start_date,
                end_date=end_date,
                process_count=None,
                log_prefix="[A股] ",
            )

            if result.failed == 0:
                logging.info("🎉 所有股票历史数据下载成功！")
                return True

            logging.warning(
                f"⚠ 部分股票下载失败，成功率: {result.success/total_stocks*100:.1f}%"
            )
            return False

        except Exception as e:
            logging.error(f"批量下载股票历史数据时发生错误: {e}")
            return False

    def download_hk_ggt_history(
        self,
        stock_id: str,
        period: PeriodType,
        start_date: str,
        end_date: str,
        adjust: AdjustType = AdjustType.HFQ,
    ) -> bool:
        """
        下载港股通(GuGangTong, GGT)香港股票历史数据

        Args:
            stock_id: 香港股票代码 (5位数字)
            period: 周期类型（日/周/月）
            start_date: 开始日期
            end_date: 结束日期
            adjust: 复权类型（默认后复权）

        Returns:
            bool: 是否成功下载并保存
        """
        table_name = get_table_name(SecurityType.HK_GGT_STOCK, period, adjust)

        return self._download_history_data(
            table_name=table_name,
            security_id=stock_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            downloader_func=self.downloader.dl_history_data_stock_hk,
            storage_save_func=get_storage().save_history_data_hk_stock,
        )

    def download_all_hk_stock_history(
        self,
        period: PeriodType = PeriodType.DAILY,
        adjust: AdjustType = AdjustType.HFQ,
        start_date: str = "2000-01-01",
        end_date: str = None,
    ) -> bool:
        """
        下载所有香港股票的历史数据

        Args:
            period: 周期类型（日/周/月）
            adjust: 复权类型（默认后复权）
            start_date: 开始日期，默认为2000-01-01
            end_date: 结束日期，默认为当天

        Returns:
            bool: 是否成功完成所有香港股票的下载
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        logging.info(
            f"开始下载所有香港股票历史数据，周期: {period.value}, 复权: {adjust.value}, 日期范围: {start_date} 到 {end_date}"
        )

        table_name = get_table_name(SecurityType.HK_GGT_STOCK, period, adjust)
        try:
            if adjust == AdjustType.QFQ:
                get_storage().drop_table(table_name)

            df_hk_stocks = get_storage().load_general_info_hk_ggt()

            if df_hk_stocks is None or df_hk_stocks.empty:
                logging.error("无法获取香港股票基本信息数据")
                return False

            stock_ids = df_hk_stocks[COL_STOCK_ID].tolist()
            total_stocks = len(stock_ids)

            logging.info(
                f"共获取到 {total_stocks} 只香港股票，开始多进程下载历史数据..."
            )

            result = run_history_download_mp(
                security_type=SecurityType.HK_GGT_STOCK,
                ids=stock_ids,
                period_value=period.value,
                adjust_value=adjust.value,
                start_date=start_date,
                end_date=end_date,
                process_count=None,
                log_prefix="[港股] ",
            )

            if result.failed == 0:
                logging.info("🎉 所有香港股票历史数据下载成功！")
                return True

            logging.warning(
                f"⚠ 部分香港股票下载失败，成功率: {result.success/total_stocks*100:.1f}%"
            )
            return False

        except Exception as e:
            logging.error(f"批量下载香港股票历史数据时发生错误: {e}")
            return False

    def download_etf_history(
        self,
        etf_id: str,
        period: PeriodType,
        start_date: str,
        end_date: str,
        adjust: AdjustType = AdjustType.QFQ,
    ) -> bool:
        """
        下载ETF历史数据

        Args:
            etf_id: ETF代码
            period: 周期类型（日/周）
            start_date: 开始日期
            end_date: 结束日期
            adjust: 复权类型（前复权/后复权）

        Returns:
            bool: 是否成功下载并保存
        """
        table_name = get_table_name(SecurityType.ETF, period, adjust)

        return self._download_history_data(
            table_name=table_name,
            security_id=etf_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            downloader_func=self.downloader.dl_history_data_etf,
            storage_save_func=get_storage().save_history_data_etf,
        )

    def download_all_etf_history(
        self,
        period: PeriodType = PeriodType.DAILY,
        adjust: AdjustType = AdjustType.QFQ,
        start_date: str = "2000-01-01",
        end_date: str = None,
    ) -> bool:
        """
        下载所有ETF的历史数据

        Args:
            period: 周期类型（日/周）
            adjust: 复权类型（前复权/后复权）
            start_date: 开始日期，默认为2000-01-01
            end_date: 结束日期，默认为当天

        Returns:
            bool: 是否成功完成所有ETF的下载
        """
        if end_date is None:
            from datetime import datetime

            end_date = datetime.now().strftime("%Y-%m-%d")

        logging.info(
            f"开始下载所有ETF历史数据，周期: {period.value}, 复权: {adjust.value}, 日期范围: {start_date} 到 {end_date}"
        )

        table_name = get_table_name(SecurityType.ETF, period, adjust)

        try:
            if adjust == AdjustType.QFQ:
                get_storage().drop_table(table_name)

            # 获取ETF基本信息
            df_etfs = get_storage().load_general_info_etf()

            if df_etfs is None or df_etfs.empty:
                logging.error("无法获取ETF基本信息数据")
                return False

            etf_ids = df_etfs[COL_STOCK_ID].tolist()
            total_etfs = len(etf_ids)

            logging.info(f"共获取到 {total_etfs} 只ETF，开始多进程下载历史数据...")

            result = run_history_download_mp(
                security_type=SecurityType.ETF,
                ids=etf_ids,
                period_value=period.value,
                adjust_value=adjust.value,
                start_date=start_date,
                end_date=end_date,
                process_count=None,
                log_prefix="[ETF] ",
            )

            if result.failed == 0:
                logging.info("🎉 所有ETF历史数据下载成功！")
                return True

            logging.warning(
                f"⚠ 部分ETF下载失败，成功率: {result.success/total_etfs*100:.1f}%"
            )
            return False

        except Exception as e:
            logging.error(f"批量下载ETF历史数据时发生错误: {e}")
            return False

    def download_ingredient_300(self) -> bool:
        """
        下载沪深300成分股数据

        Returns:
            bool: 是否成功下载并保存
        """
        get_storage().drop_table(tb_name_ingredient_300)

        try:
            # 下载沪深300成分股数据
            df = self.downloader.dl_ingredient_300()
            if df is None or df.empty:
                logging.warning(
                    "Failed to download CSI 300 ingredient data or data is empty."
                )
                return False

            # 保存数据到数据库
            return get_storage().save_ingredient_300(df)

        except Exception as e:
            logging.error(f"下载沪深300成分股数据时出错: {e}")
            return False

    def download_ingredient_500(self) -> bool:
        """
        下载中证500成分股数据

        Returns:
            bool: 是否成功下载并保存
        """
        get_storage().drop_table(tb_name_ingredient_500)

        try:
            df = self.downloader.dl_ingredient_500()
            if df is None or df.empty:
                logging.warning(
                    "Failed to download CSI 500 ingredient data or data is empty."
                )
                return False

            return get_storage().save_ingredient_500(df)

        except Exception as e:
            logging.error(f"下载中证500成分股数据时出错: {e}")
            return False

    def download_daily_basic_a_stock(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> bool:
        """
        下载A股每日基本面数据（daily_basic）

        Args:
            trade_date: 交易日期，默认为当天（格式：YYYY-MM-DD 或 YYYYMMDD）

        Returns:
            bool: 是否成功下载并保存
        """
        last_record = get_storage().get_last_record(tb_name_daily_basic_a_stock)

        if start_date is None:
            start_date = "2010-01-01"

        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if last_record is not None:
            latest_date = pd.Timestamp(last_record[COL_DATE])
            actual_start_ts = latest_date + pd.Timedelta(days=1)
            actual_start_date = actual_start_ts.strftime("%Y%m%d")

            if actual_start_ts > pd.to_datetime(end_date):
                logging.info("A股每日基本面数据已是最新，无需下载")
                return True
        else:
            actual_start_date = start_date

        market_calendar = mcal.get_calendar("XSHG")
        trade_days = market_calendar.schedule(
            start_date=actual_start_date, end_date=end_date
        )

        try:
            total_days = len(trade_days)
            logging.info(f"需要下载 {total_days} 个交易日的每日基本面数据")

            for i, date in enumerate(trade_days.index, 1):
                trade_date = date.strftime("%Y-%m-%d")

                df = self.downloader.dl_daily_basic_a_stock(trade_date)
                if df is None or df.empty:
                    logging.info(f"日期 {trade_date} 无数据，跳过")
                    continue

                get_storage().save_daily_basic_a_stock(df)

                if i % 50 == 0:
                    logging.info(f"进度: {i}/{total_days} ({i/total_days*100:.1f}%)")

            logging.info(f"每日基本面数据下载完成，共处理 {total_days} 个交易日")
            return True
        except Exception as e:
            logging.error(f"下载A股每日基本面数据时出错: {e}")
            return False

    def download_stk_limit_a_stock(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> bool:
        """
        下载A股涨跌停价格数据（stk_limit）

        Args:
            start_date: 开始日期，默认为2010-01-01
            end_date: 结束日期，默认为当天

        Returns:
            bool: 是否成功下载并保存
        """
        last_record = get_storage().get_last_record(tb_name_stk_limit_a_stock)

        if start_date is None:
            start_date = "2010-01-01"

        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if last_record is not None:
            latest_date = pd.Timestamp(last_record[COL_DATE])
            actual_start_ts = latest_date + pd.Timedelta(days=1)
            actual_start_date = actual_start_ts.strftime("%Y%m%d")

            if actual_start_ts > pd.to_datetime(end_date):
                logging.info("A股涨跌停价格数据已是最新，无需下载")
                return True
        else:
            actual_start_date = start_date

        market_calendar = mcal.get_calendar("XSHG")
        trade_days = market_calendar.schedule(
            start_date=actual_start_date, end_date=end_date
        )

        try:
            total_days = len(trade_days)
            logging.info(f"需要下载 {total_days} 个交易日的涨跌停价格数据")

            for i, date in enumerate(trade_days.index, 1):
                trade_date = date.strftime("%Y-%m-%d")

                df = self.downloader.dl_stk_limit_a_stock(trade_date=trade_date)
                if df is None or df.empty:
                    logging.info(f"日期 {trade_date} 无数据，跳过")
                    continue

                get_storage().save_stk_limit_a_stock(df)

                if i % 50 == 0:
                    logging.info(f"进度: {i}/{total_days} ({i/total_days*100:.1f}%)")

            logging.info(f"涨跌停价格数据下载完成，共处理 {total_days} 个交易日")
            return True
        except Exception as e:
            logging.error(f"下载A股涨跌停价格数据时出错: {e}")
            return False

    def download_suspend_d_a_stock(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> bool:
        """
        下载A股停复牌数据（suspend_d）

        Args:
            start_date: 开始日期，默认为2010-01-01
            end_date: 结束日期，默认为当天

        Returns:
            bool: 是否成功下载并保存
        """
        last_record = get_storage().get_last_record(tb_name_suspend_d_a_stock)

        if start_date is None:
            start_date = "2010-01-01"

        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if last_record is not None:
            latest_date = pd.Timestamp(last_record[COL_DATE])
            actual_start_ts = latest_date + pd.Timedelta(days=1)
            actual_start_date = actual_start_ts.strftime("%Y%m%d")

            if actual_start_ts > pd.to_datetime(end_date):
                logging.info("A股停复牌数据已是最新，无需下载")
                return True
        else:
            actual_start_date = start_date

        market_calendar = mcal.get_calendar("XSHG")
        trade_days = market_calendar.schedule(
            start_date=actual_start_date, end_date=end_date
        )

        try:
            total_days = len(trade_days)
            logging.info(f"需要下载 {total_days} 个交易日的停复牌数据")

            for i, date in enumerate(trade_days.index, 1):
                trade_date = date.strftime("%Y-%m-%d")

                # 下载停牌数据 (suspend_type='S')
                df_suspend = self.downloader.dl_suspend_d_a_stock(
                    suspend_type="S", trade_date=trade_date
                )
                if df_suspend is not None and not df_suspend.empty:
                    get_storage().save_suspend_d_a_stock(df_suspend)

                # 下载复牌数据 (suspend_type='R')
                df_resume = self.downloader.dl_suspend_d_a_stock(
                    suspend_type="R", trade_date=trade_date
                )
                if df_resume is not None and not df_resume.empty:
                    get_storage().save_suspend_d_a_stock(df_resume)

                if i % 50 == 0:
                    logging.info(f"进度: {i}/{total_days} ({i/total_days*100:.1f}%)")

            logging.info(f"停复牌数据下载完成，共处理 {total_days} 个交易日")
            return True
        except Exception as e:
            logging.error(f"下载A股停复牌数据时出错: {e}")
            return False

    def download_a_stock_basic(self, list_status: str = "L") -> bool:
        """
        下载A股基础信息数据（stock_basic）

        Args:
            list_status: 上市状态，默认为"L"（上市）
                      L-上市 D-退市 P-暂停上市 G-过会未交易

        Returns:
            bool: 是否成功下载并保存
        """
        get_storage().drop_table(tb_name_a_stock_basic)

        try:
            df = self.downloader.dl_a_stock_basic(list_status=list_status)
            if df is None or df.empty:
                logging.warning(
                    "Failed to download A-stock basic info or data is empty."
                )
                return False

            logging.info(f"成功下载 {len(df)} 条A股基础信息数据")
            return get_storage().save_a_stock_basic(df)

        except Exception as e:
            logging.error(f"下载A股基础信息数据时出错: {e}")
            return False
