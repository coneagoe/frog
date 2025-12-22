#!/usr/bin/env python3
import os
import sys

import pandas as pd
import psycopg2
from sqlalchemy import create_engine

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.config import StorageConfig  # noqa: E402
from storage.model import (  # noqa: E402
    tb_name_general_info_stock,
    tb_name_history_data_daily_a_stock_qfq,
)


def get_db_connection():
    """获取数据库连接"""
    config = StorageConfig()
    config.db_name = "quant"
    config.db_username = "quant"
    config.db_password = "quant"

    return psycopg2.connect(
        host=config.db_host,
        port=config.db_port,
        database=config.db_name,
        user=config.db_username,
        password=config.db_password,
    )


def show_tables():
    """显示所有表"""
    print("📋 数据库中的表：")
    print("=" * 50)

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 查询表信息
        cur.execute(
            """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
            """
        )

        tables = cur.fetchall()
        print(f"共找到 {len(tables)} 个表：")
        for table_name, table_type in tables:
            print(f"  📊 {table_name} ({table_type})")

            # 显示每个表的记录数
            cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            count = cur.fetchone()[0]
            print(f"     └─ 记录数: {count}")

            if count > 0 and table_name == "history_data_daily_a_stock":
                # 显示数据的时间范围
                cur.execute(f'SELECT MIN("日期"), MAX("日期") FROM "{table_name}"')
                min_date, max_date = cur.fetchone()
                print(f"     └─ 数据范围: {min_date} 到 {max_date}")

                # 显示包含的股票代码
                cur.execute(f'SELECT COUNT(DISTINCT "股票代码") FROM "{table_name}"')
                stock_count = cur.fetchone()[0]
                print(f"     └─ 股票数量: {stock_count} 支")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ 查询失败: {e}")


def show_table_structure(table_name):
    """显示表结构"""
    print(f"\n🔍 表 '{table_name}' 的结构：")
    print("=" * 50)

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 查询列信息
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """,
            (table_name,),
        )

        columns = cur.fetchall()

        # 显示为格式化表格
        print(f"{'列名':<20} {'数据类型':<15} {'可空':<8} {'默认值':<20}")
        print("-" * 60)
        for col_name, data_type, is_nullable, col_default in columns:
            nullable_str = "是" if is_nullable == "YES" else "否"
            default_str = str(col_default) if col_default else ""
            print(f"{col_name:<20} {data_type:<15} {nullable_str:<8} {default_str:<20}")

        # 显示索引信息
        cur.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = %s;
            """,
            (table_name,),
        )

        indexes = cur.fetchall()
        if indexes:
            print("\n🔑 索引:")
            for idx_name, idx_def in indexes:
                print(f"  ├─ {idx_name}")
                print(f"  │  └─ {idx_def[:100]}...")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ 查询失败: {e}")


def show_sample_data(table_name, limit=5):
    """显示样例数据"""
    print(f"\n📊 表 '{table_name}' 的样例数据（前{limit}条）：")
    print("=" * 50)

    try:
        # 使用SQLAlchemy引擎避免pandas警告
        config = StorageConfig()
        sqlalchemy_url = (
            f"postgresql://{config.db_username}:{config.db_password}@"
            f"{config.db_host}:{config.db_port}/{config.db_name}"
        )
        engine = create_engine(sqlalchemy_url, echo=False)

        df = pd.read_sql(f'SELECT * FROM "{table_name}" LIMIT {limit}', engine)

        if df.empty:
            print("表中没有数据")
        else:
            print(df.to_string())

            # 统计信息
            print("\n📈 统计信息：")
            total_count = pd.read_sql(
                f'SELECT COUNT(*) as count FROM "{table_name}"', engine
            )["count"].iloc[0]
            print(f"  📍 总记录数: {total_count}")

            date_cols = [
                col for col in df.columns if "日期" in col or "date" in col.lower()
            ]
            if date_cols:
                date_col = date_cols[0]
                date_stats = pd.read_sql(
                    f"""
                    SELECT
                        MIN("{date_col}") as 最早日期,
                        MAX("{date_col}") as 最晚日期,
                        COUNT(DISTINCT "{date_col}") as 日期数量
                    FROM "{table_name}"
                    """,
                    engine,
                )
                print(
                    f"  📅 日期范围: {date_stats['最早日期'].iloc[0]} 到 {date_stats['最晚日期'].iloc[0]}"
                )
                print(f"  📅 不重复日期数: {date_stats['日期数量'].iloc[0]}")

        engine.dispose()

    except Exception as e:
        print(f"❌ 查询失败: {e}")


def query_specific_stock(table_name, stock_code, limit=5):
    """查询指定表中指定的股票，显示前N条和后N条记录"""
    print(f"\n🔍 查询表 '{table_name}' 中股票代码 '{stock_code}' 的数据：")
    print("=" * 60)

    try:
        # 使用SQLAlchemy引擎避免pandas警告
        config = StorageConfig()
        sqlalchemy_url = (
            f"postgresql://{config.db_username}:{config.db_password}@"
            f"{config.db_host}:{config.db_port}/{config.db_name}"
        )
        engine = create_engine(sqlalchemy_url, echo=False)

        # 首先检查表是否存在以及是否有股票代码列
        check_query = f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = '{table_name}'
        AND column_name IN ('股票代码', 'stock_code', 'code')
        """

        check_df = pd.read_sql(check_query, engine)
        if check_df.empty:
            print(
                f"❌ 表 '{table_name}' 中没有找到股票代码列（股票代码/stock_code/code）"
            )
            engine.dispose()
            return

        # 获取股票代码列名
        stock_code_column = check_df.iloc[0]["column_name"]

        # 获取该股票的总记录数
        count_query = f"""
        SELECT COUNT(*) as count
        FROM "{table_name}"
        WHERE "{stock_code_column}" = '{stock_code}'
        """
        total_count = pd.read_sql(count_query, engine)["count"].iloc[0]

        if total_count == 0:
            print(f"❌ 在表 '{table_name}' 中没有找到股票代码 '{stock_code}' 的数据")
            engine.dispose()
            return

        print(f"📊 该股票在表中的总记录数: {total_count}")

        # 查询前N条记录
        print(f"\n📈 前{limit}条记录：")
        print("-" * 40)
        first_query = f"""
        SELECT * FROM "{table_name}"
        WHERE "{stock_code_column}" = '{stock_code}'
        ORDER BY 1 ASC
        LIMIT {limit}
        """
        first_df = pd.read_sql(first_query, engine)
        print(first_df.to_string())

        # 如果总记录数大于limit，再查询后N条记录
        if total_count > limit:
            print(f"\n📈 后{limit}条记录：")
            print("-" * 40)
            last_query = f"""
            SELECT * FROM (
                SELECT * FROM "{table_name}"
                WHERE "{stock_code_column}" = '{stock_code}'
                ORDER BY 1 DESC
                LIMIT {limit}
            ) AS last_records
            ORDER BY 1 ASC
            """
            last_df = pd.read_sql(last_query, engine)
            print(last_df.to_string())

        # 如果有日期列，显示日期范围
        date_cols = [
            col for col in first_df.columns if "日期" in col or "date" in col.lower()
        ]
        if date_cols:
            date_col = date_cols[0]
            date_stats_query = f"""
            SELECT
                MIN("{date_col}") as 最早日期,
                MAX("{date_col}") as 最晚日期
            FROM "{table_name}"
            WHERE "{stock_code_column}" = '{stock_code}'
            """
            date_stats = pd.read_sql(date_stats_query, engine)
            print(
                f"\n📅 数据日期范围: {date_stats['最早日期'].iloc[0]} 到 {date_stats['最晚日期'].iloc[0]}"
            )

        engine.dispose()

    except Exception as e:
        print(f"❌ 查询失败: {e}")


def show_raw_command_examples():
    """显示一些基础的PostgreSQL命令行示例"""
    print("\n=== 基本命令行查看方法 ===")
    print("1. 查看所有表:")
    print('   sudo docker exec -it frog-db-1 psql -U quant -d quant -c "\\dt"')
    print("\n2. 查看表结构:")
    print(
        '   sudo docker exec -it frog-db-1 psql -U quant -d quant -c "\\d history_data_daily_a_stock"'
    )
    print("\n3. 查看数据数量:")
    print(
        '   sudo docker exec -it frog-db-1 psql -U quant -d quant -c "SELECT COUNT(*) FROM history_data_daily_a_stock;"'
    )
    print("\n4. 查看前5条数据:")
    print(
        "   sudo docker exec -it frog-db-1 psql -U quant -d quant -c "
        '"SELECT * FROM history_data_daily_a_stock LIMIT 5;"'
    )
    print("\n5. 进入交互式SQL控制台:")
    print("   sudo docker exec -it frog-db-1 psql -U quant -d quant")


def main_menu():
    """主菜单"""
    while True:
        print("\n" + "=" * 60)
        print("🛠️  数据库管理工具")
        print("=" * 60)
        print("1. 📋 显示所有表")
        print("2. 🔍 查看表结构")
        print("3. 📊 查看样例数据")
        print("4. 🔍 查询指定股票数据")
        print("5. ❓ 显示基本命令行示例")
        print("6. ❌ 退出")
        print("=" * 60)

        choice = input("\n请选择操作 (1-6): ").strip()

        if choice == "1":
            show_tables()
        elif choice == "2":
            table_name = input(
                f"请输入表名 (默认: {tb_name_general_info_stock}): "
            ).strip()
            if not table_name:
                table_name = tb_name_general_info_stock
            show_table_structure(table_name)
        elif choice == "3":
            table_name = input(
                f"请输入表名 (默认: {tb_name_history_data_daily_a_stock_qfq}): "
            ).strip()
            if not table_name:
                table_name = tb_name_history_data_daily_a_stock_qfq
            limit_str = input("显示多少条记录 (默认: 5): ").strip()
            limit = int(limit_str) if limit_str.isdigit() else 5
            show_sample_data(table_name, limit)
        elif choice == "4":
            table_name = input(
                f"请输入表名 (默认: {tb_name_history_data_daily_a_stock_qfq}): "
            ).strip()
            if not table_name:
                table_name = tb_name_history_data_daily_a_stock_qfq
            stock_code = input("请输入股票代码: ").strip()
            if not stock_code:
                print("❌ 股票代码不能为空")
                continue
            limit_str = input("显示前/后多少条记录 (默认: 5): ").strip()
            limit = int(limit_str) if limit_str.isdigit() else 5
            query_specific_stock(table_name, stock_code, limit)
        elif choice == "5":
            show_raw_command_examples()
        elif choice == "6":
            print("👋 再见！")
            break
        else:
            print("❌ 无效的选择，请重新输入")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n👋 用户中断操作")
    except Exception as e:
        print(f"❌ 程序错误: {e}")
