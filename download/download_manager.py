import logging

import pandas as pd

from common.const import COL_DATE, COL_STOCK_ID, AdjustType, PeriodType
from storage import (
    get_storage,
    tb_name_general_info_stock,
    tb_name_history_data_daily_a_stock_hfq,
    tb_name_history_data_daily_a_stock_qfq,
    tb_name_history_data_daily_hk_stock_hfq,
    tb_name_history_data_monthly_hk_stock_hfq,
    tb_name_history_data_weekly_a_stock_hfq,
    tb_name_history_data_weekly_a_stock_qfq,
    tb_name_history_data_weekly_hk_stock_hfq,
    tb_name_ingredient_300,
    tb_name_ingredient_500,
)
from storage.model import (
    tb_name_history_data_daily_etf_hfq,
    tb_name_history_data_daily_etf_qfq,
    tb_name_history_data_weekly_etf_hfq,
    tb_name_history_data_weekly_etf_qfq,
)

from .dl import Downloader


class DownloadManager:
    def __init__(self):
        storage = get_storage()

        self.storage = storage
        self.downloader = Downloader()

    def download_general_info_stock(self, force: bool = False) -> bool:
        self.storage.drop_table(tb_name_general_info_stock)

        df = self.downloader.dl_general_info_stock()
        if df is None or df.empty:
            logging.warning("Failed to download stock info or data is empty.")
            return False

        return self.storage.save_general_info_stock(df)

    def download_general_info_etf(self, force: bool = False) -> bool:
        df = self.downloader.dl_general_info_etf()
        if df is None or df.empty:
            logging.warning("Failed to download ETF info or data is empty.")
            return False

        return self.storage.save_general_info_etf(df)

    def download_general_info_hk_ggt(self, force: bool = False) -> bool:
        df = self.downloader.dl_general_info_hk_ggt_stock()
        if df is None or df.empty:
            logging.warning("Failed to download HK GGT info or data is empty.")
            return False

        return self.storage.save_general_info_hk_ggt(df)

    def download_stock_history(
        self,
        stock_id: str,
        period: PeriodType,
        start_date: str,
        end_date: str,
        adjust: AdjustType = AdjustType.QFQ,
    ) -> bool:
        if adjust == AdjustType.QFQ:
            table_name = (
                tb_name_history_data_daily_a_stock_qfq
                if period == PeriodType.DAILY
                else tb_name_history_data_weekly_a_stock_qfq
            )
        else:
            table_name = (
                tb_name_history_data_daily_a_stock_hfq
                if period == PeriodType.DAILY
                else tb_name_history_data_weekly_a_stock_hfq
            )

        try:
            last_record = self.storage.get_last_record(table_name, stock_id)

            if last_record is not None:
                latest_date = pd.Timestamp(last_record[COL_DATE])
                actual_start_date = (latest_date + pd.Timedelta(days=1)).strftime(
                    "%Y%m%d"
                )

                if actual_start_date > end_date:
                    logging.info(f"Data for {stock_id} is already up to date")
                    return True
            else:
                actual_start_date = start_date

            df = self.downloader.dl_history_data_stock(
                stock_id, actual_start_date, end_date, period, adjust
            )

            if df is None or df.empty:
                logging.info(f"No new data for {stock_id}")
                return True

            return self.storage.save_history_data_stock(df, period, adjust)

        except Exception as e:
            logging.error(f"Error processing history for {stock_id}: {e}")
            return False

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
            from datetime import datetime

            end_date = datetime.now().strftime("%Y-%m-%d")

        logging.info(
            f"开始下载所有股票历史数据，周期: {period.value}, 复权: {adjust.value}, 日期范围: {start_date} 到 {end_date}"
        )

        try:
            if adjust == AdjustType.QFQ:
                table_name = (
                    tb_name_history_data_daily_a_stock_qfq
                    if period == PeriodType.DAILY
                    else tb_name_history_data_weekly_a_stock_qfq
                )
                self.storage.drop_table(table_name)

            df_stocks = self.storage.load_general_info_stock()

            if df_stocks is None or df_stocks.empty:
                logging.error("无法获取股票基本信息数据")
                return False

            stock_ids = df_stocks[COL_STOCK_ID].tolist()
            total_stocks = len(stock_ids)

            logging.info(f"共获取到 {total_stocks} 只股票，开始批量下载历史数据...")

            success_count = 0
            failure_count = 0

            for i, stock_id in enumerate(stock_ids, 1):
                try:
                    logging.info(f"正在下载第 {i}/{total_stocks} 只股票: {stock_id}")

                    success = self.download_stock_history(
                        stock_id=stock_id,
                        period=period,
                        start_date=start_date,
                        end_date=end_date,
                        adjust=adjust,
                    )

                    if success:
                        success_count += 1
                        logging.info(f"✓ 股票 {stock_id} 下载成功 ({i}/{total_stocks})")
                    else:
                        failure_count += 1
                        logging.warning(
                            f"⚠ 股票 {stock_id} 下载失败 ({i}/{total_stocks})"
                        )

                except Exception as e:
                    failure_count += 1
                    logging.error(
                        f"✗ 股票 {stock_id} 下载出错: {e} ({i}/{total_stocks})"
                    )

            # 总结下载结果
            logging.info(
                f"批量下载完成！成功: {success_count}, 失败: {failure_count}, 总计: {total_stocks}"
            )

            if failure_count == 0:
                logging.info("🎉 所有股票历史数据下载成功！")
                return True
            else:
                logging.warning(
                    f"⚠ 部分股票下载失败，成功率: {success_count/total_stocks*100:.1f}%"
                )
                return False

        except Exception as e:
            logging.error(f"批量下载股票历史数据时发生错误: {e}")
            return False

    def download_hk_stock_history(
        self,
        stock_id: str,
        period: PeriodType,
        start_date: str,
        end_date: str,
        adjust: AdjustType = AdjustType.HFQ,
    ) -> bool:
        """
        下载香港股票历史数据

        Args:
            stock_id: 香港股票代码 (5位数字)
            period: 周期类型（日/周/月）
            start_date: 开始日期
            end_date: 结束日期
            adjust: 复权类型（默认后复权）

        Returns:
            bool: 是否成功下载并保存
        """
        # 根据周期选择对应的表名
        if period == PeriodType.DAILY:
            table_name = tb_name_history_data_daily_hk_stock_hfq
        elif period == PeriodType.WEEKLY:
            table_name = tb_name_history_data_weekly_hk_stock_hfq
        elif period == PeriodType.MONTHLY:
            table_name = tb_name_history_data_monthly_hk_stock_hfq
        else:
            logging.error(f"不支持的周期类型: {period}")
            return False

        try:
            # 获取最后一条记录以实现增量更新
            last_record = self.storage.get_last_record(table_name, stock_id)

            if last_record is not None:
                latest_date = pd.Timestamp(last_record[COL_DATE])
                actual_start_date = (latest_date + pd.Timedelta(days=1)).strftime(
                    "%Y-%m-%d"
                )

                if actual_start_date > end_date:
                    logging.info(f"香港股票 {stock_id} 数据已是最新")
                    return True
            else:
                actual_start_date = start_date

            # 下载香港股票历史数据
            df = self.downloader.dl_history_data_stock_hk(
                stock_id, actual_start_date, end_date, period, adjust
            )

            if df is None or df.empty:
                logging.info(f"香港股票 {stock_id} 无新数据")
                return True

            # 保存数据到对应的香港股票历史数据表
            return self.storage.save_history_data_hk_stock(df, period, adjust)

        except Exception as e:
            logging.error(f"处理香港股票 {stock_id} 历史数据时出错: {e}")
            return False

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
            from datetime import datetime

            end_date = datetime.now().strftime("%Y-%m-%d")

        logging.info(
            f"开始下载所有香港股票历史数据，周期: {period.value}, 复权: {adjust.value}, 日期范围: {start_date} 到 {end_date}"
        )

        try:
            if adjust == AdjustType.QFQ:
                table_name = (
                    tb_name_history_data_daily_hk_stock_hfq
                    if period == PeriodType.DAILY
                    else tb_name_history_data_weekly_hk_stock_hfq
                )
                self.storage.drop_table(table_name)

            df_hk_stocks = self.storage.load_general_info_hk_ggt()

            if df_hk_stocks is None or df_hk_stocks.empty:
                logging.error("无法获取香港股票基本信息数据")
                return False

            stock_ids = df_hk_stocks[COL_STOCK_ID].tolist()
            total_stocks = len(stock_ids)

            logging.info(f"共获取到 {total_stocks} 只香港股票，开始批量下载历史数据...")

            success_count = 0
            failure_count = 0

            for i, stock_id in enumerate(stock_ids, 1):
                try:
                    logging.info(
                        f"正在下载第 {i}/{total_stocks} 只香港股票: {stock_id}"
                    )

                    success = self.download_hk_stock_history(
                        stock_id=stock_id,
                        period=period,
                        start_date=start_date,
                        end_date=end_date,
                        adjust=adjust,
                    )

                    if success:
                        success_count += 1
                        logging.info(
                            f"✓ 香港股票 {stock_id} 下载成功 ({i}/{total_stocks})"
                        )
                    else:
                        failure_count += 1
                        logging.warning(
                            f"⚠ 香港股票 {stock_id} 下载失败 ({i}/{total_stocks})"
                        )

                except Exception as e:
                    failure_count += 1
                    logging.error(
                        f"✗ 香港股票 {stock_id} 下载出错: {e} ({i}/{total_stocks})"
                    )

            # 总结下载结果
            logging.info(
                f"香港股票批量下载完成！成功: {success_count}, 失败: {failure_count}, 总计: {total_stocks}"
            )

            if failure_count == 0:
                logging.info("🎉 所有香港股票历史数据下载成功！")
                return True
            else:
                logging.warning(
                    f"⚠ 部分香港股票下载失败，成功率: {success_count/total_stocks*100:.1f}%"
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
        # 根据复权类型选择对应的表名
        if adjust == AdjustType.QFQ:
            table_name = (
                tb_name_history_data_daily_etf_qfq
                if period == PeriodType.DAILY
                else tb_name_history_data_weekly_etf_qfq
            )
        else:
            table_name = (
                tb_name_history_data_daily_etf_hfq
                if period == PeriodType.DAILY
                else tb_name_history_data_weekly_etf_hfq
            )

        try:
            # 获取最后一条记录以实现增量更新
            last_record = self.storage.get_last_record(table_name, etf_id)

            if last_record is not None:
                latest_date = pd.Timestamp(last_record[COL_DATE])
                actual_start_date = (latest_date + pd.Timedelta(days=1)).strftime(
                    "%Y%m%d"
                )

                if actual_start_date > end_date:
                    logging.info(f"ETF {etf_id} 数据已是最新")
                    return True
            else:
                actual_start_date = start_date

            # 下载ETF历史数据
            df = self.downloader.dl_history_data_etf(
                etf_id, actual_start_date, end_date, period, adjust
            )

            if df is None or df.empty:
                logging.info(f"ETF {etf_id} 无新数据")
                return True

            # 保存数据到对应的ETF历史数据表
            return self.storage.save_history_data_etf(df, period, adjust)

        except Exception as e:
            logging.error(f"处理ETF {etf_id} 历史数据时出错: {e}")
            return False

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

        try:
            if adjust == AdjustType.QFQ:
                table_name = (
                    tb_name_history_data_daily_etf_qfq
                    if period == PeriodType.DAILY
                    else tb_name_history_data_weekly_etf_qfq
                )
                self.storage.drop_table(table_name)

            # 获取ETF基本信息
            df_etfs = self.storage.load_general_info_etf()

            if df_etfs is None or df_etfs.empty:
                logging.error("无法获取ETF基本信息数据")
                return False

            etf_ids = df_etfs[COL_STOCK_ID].tolist()
            total_etfs = len(etf_ids)

            logging.info(f"共获取到 {total_etfs} 只ETF，开始批量下载历史数据...")

            success_count = 0
            failure_count = 0

            for i, etf_id in enumerate(etf_ids, 1):
                try:
                    logging.info(f"正在下载第 {i}/{total_etfs} 只ETF: {etf_id}")

                    success = self.download_etf_history(
                        etf_id=etf_id,
                        period=period,
                        start_date=start_date,
                        end_date=end_date,
                        adjust=adjust,
                    )

                    if success:
                        success_count += 1
                        logging.info(f"✓ ETF {etf_id} 下载成功 ({i}/{total_etfs})")
                    else:
                        failure_count += 1
                        logging.warning(f"⚠ ETF {etf_id} 下载失败 ({i}/{total_etfs})")

                except Exception as e:
                    failure_count += 1
                    logging.error(f"✗ ETF {etf_id} 下载出错: {e} ({i}/{total_etfs})")

            # 总结下载结果
            logging.info(
                f"ETF批量下载完成！成功: {success_count}, 失败: {failure_count}, 总计: {total_etfs}"
            )

            if failure_count == 0:
                logging.info("🎉 所有ETF历史数据下载成功！")
                return True
            else:
                logging.warning(
                    f"⚠ 部分ETF下载失败，成功率: {success_count/total_etfs*100:.1f}%"
                )
                return False

        except Exception as e:
            logging.error(f"批量下载ETF历史数据时发生错误: {e}")
            return False

    def download_ingredient_300(self) -> bool:
        """
        下载沪深300成分股数据

        Args:
            force: 是否强制重新下载（删除现有数据）

        Returns:
            bool: 是否成功下载并保存
        """
        self.storage.drop_table(tb_name_ingredient_300)

        try:
            # 下载沪深300成分股数据
            df = self.downloader.dl_ingredient_300()
            if df is None or df.empty:
                logging.warning(
                    "Failed to download CSI 300 ingredient data or data is empty."
                )
                return False

            # 保存数据到数据库
            return self.storage.save_ingredient_300(df)

        except Exception as e:
            logging.error(f"下载沪深300成分股数据时出错: {e}")
            return False

    def download_ingredient_500(self) -> bool:
        """
        下载中证500成分股数据

        Args:
            force: 是否强制重新下载（删除现有数据）

        Returns:
            bool: 是否成功下载并保存
        """
        self.storage.drop_table(tb_name_ingredient_500)

        try:
            # 下载中证500成分股数据
            df = self.downloader.dl_ingredient_500()
            if df is None or df.empty:
                logging.warning(
                    "Failed to download CSI 500 ingredient data or data is empty."
                )
                return False

            # 保存数据到数据库
            return self.storage.save_ingredient_500(df)

        except Exception as e:
            logging.error(f"下载中证500成分股数据时出错: {e}")
            return False
