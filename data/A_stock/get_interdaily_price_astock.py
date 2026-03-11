from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
import logging

import pandas as pd
import efinance as ef


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AStockIntradayDataFetcher:
    """A股盘中数据获取器
    
    用于批量获取A股市场的盘中K线数据，支持自定义时间周期和日期范围。
    支持增量更新，自动检测已有数据并从最后日期的下一天开始获取。
    
    Attributes:
        frequency: K线周期（分钟），默认60分钟
        data_dir: 数据存储目录
        stock_list_file: 股票列表文件名
        output_file: 输出文件名
    """
    
    def __init__(
        self,
        frequency: int = 60,
        data_dir: Optional[Path] = None,
        stock_list_file: str = "sse_50_weight.csv",
        output_file: str = "A_stock_hourly.csv"
    ) -> None:
        """初始化数据获取器
        
        Args:
            frequency: K线周期（分钟），默认60分钟
            data_dir: 数据目录路径，默认为 A_stock_data 子目录
            stock_list_file: 股票列表CSV文件名（相对于脚本所在目录），默认为 sse_50_weight.csv
            output_file: 输出文件名
        """
        self.frequency = frequency
        
        # 设置数据目录：默认为 A_stock_data 子目录
        if data_dir is None:
            script_dir = Path(__file__).parent
            self.data_dir = script_dir / "A_stock_data"
        else:
            self.data_dir = Path(data_dir)
        
        # 创建数据目录（如果不存在）
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 股票列表文件在 A_stock_data 目录
        self.stock_list_file = stock_list_file
        self.stock_list_path = Path(__file__).parent / "A_stock_data" / stock_list_file
        
        # 输出文件在数据目录
        self.output_file = output_file
        self.output_path = self.data_dir / output_file
        
        logger.info(f"初始化数据获取器: frequency={frequency}分钟, data_dir={self.data_dir}")
    
    def load_stock_list(self) -> List[str]:
        """从CSV文件加载股票代码列表
        
        从 sse_50_weight.csv 文件中读取 con_code 列，提取上证50成分股代码。
        
        Returns:
            股票代码列表（不含后缀，如 '600519'）
            
        Raises:
            FileNotFoundError: 当股票列表文件不存在时
        """
        if not self.stock_list_path.exists():
            raise FileNotFoundError(f"股票列表文件不存在: {self.stock_list_path}")
        
        logger.info(f"从 {self.stock_list_path} 加载股票列表")
        df = pd.read_csv(self.stock_list_path)
        
        # 从 con_code 列提取唯一的股票代码
        if "con_code" not in df.columns:
            raise ValueError(f"文件 {self.stock_list_path} 中缺少 'con_code' 列")
        
        stock_list = df["con_code"].unique()
        
        # 去除 .SH 或 .SZ 后缀
        stock_list = [code.replace(".SH", "").replace(".SZ", "") for code in stock_list]
        
        logger.info(f"成功加载 {len(stock_list)} 只股票")
        logger.debug(f"股票列表: {stock_list[:5]}..." if len(stock_list) > 5 else f"股票列表: {stock_list}")
        
        return stock_list
    
    def get_date_range(self, default_start_date: str = "20251001") -> Tuple[str, str]:
        """获取数据日期范围
        
        如果输出文件已存在，则从文件中最后一天的下一天开始；
        否则使用默认开始日期。结束日期始终为今天。
        
        Args:
            default_start_date: 默认开始日期，格式 'YYYYMMDD'
            
        Returns:
            Tuple[str, str]: (begin_date, end_date) 格式为 'YYYYMMDD'
        """
        # 结束日期始终为今天
        end_date = datetime.now().strftime("%Y%m%d")
        
        # 检查输出文件是否存在
        if self.output_path.exists():
            try:
                logger.info(f"检测到已存在的数据文件: {self.output_path}")
                df_existing = pd.read_csv(self.output_path)
                
                if not df_existing.empty and 'trade_date' in df_existing.columns:
                    # 获取最后一条记录的日期
                    # trade_date格式: "2025-10-09 10:30"
                    last_date_str = df_existing['trade_date'].max()
                    
                    # 提取日期部分（去掉时间）
                    last_date = datetime.strptime(last_date_str.split()[0], "%Y-%m-%d")
                    
                    # 计算下一天
                    next_date = last_date + timedelta(days=1)
                    begin_date = next_date.strftime("%Y%m%d")
                    
                    logger.info(f"已有数据的最后日期: {last_date.strftime('%Y-%m-%d')}")
                    logger.info(f"将从 {begin_date} 开始增量更新")
                    
                    # 检查是否已经是最新数据
                    if begin_date > end_date:
                        logger.info("数据已是最新，无需更新")
                        return begin_date, end_date
                    
                    return begin_date, end_date
                else:
                    logger.warning("已有文件为空或缺少trade_date列，使用默认开始日期")
                    return default_start_date, end_date
                    
            except Exception as e:
                logger.warning(f"读取已有数据文件失败: {e}，使用默认开始日期")
                return default_start_date, end_date
        else:
            logger.info(f"未检测到已有数据文件，将从 {default_start_date} 开始获取")
            return default_start_date, end_date
    
    def fetch_intraday_data(
        self,
        stock_list: List[str],
        begin_date: str,
        end_date: str
    ) -> dict:
        """批量获取股票盘中数据
        
        Args:
            stock_list: 股票代码列表
            begin_date: 开始日期，格式 'YYYYMMDD'
            end_date: 结束日期，格式 'YYYYMMDD'（通常为当天日期）
            
        Returns:
            包含所有股票数据的字典，key为股票代码，value为DataFrame
        """
        logger.info(f"开始获取 {len(stock_list)} 只股票的盘中数据")
        logger.info(f"时间范围: {begin_date} - {end_date}, 周期: {self.frequency}分钟")
        
        try:
            df_dict = ef.stock.get_quote_history(
                stock_list,
                klt=self.frequency,
                beg=begin_date,
                end=end_date
            )
            logger.info("数据获取成功")
            return df_dict
        except Exception as e:
            logger.error(f"数据获取失败: {e}")
            raise
    
    def process_and_save_data(
        self,
        df_dict: dict,
        is_incremental: bool = False
    ) -> pd.DataFrame:
        """处理并保存数据
        
        将字典格式的数据整合为单个DataFrame，统一列名并保存。
        支持增量更新模式，新数据会追加到已有数据中。
        
        Args:
            df_dict: 股票数据字典
            is_incremental: 是否为增量更新模式
            
        Returns:
            整合后的DataFrame
        """
        logger.info("开始处理数据")
        
        df_new = pd.DataFrame()
        
        # 遍历每只股票的数据
        for stock_code, df_one in df_dict.items():
            df_new = pd.concat([df_new, df_one], ignore_index=True)
        
        # 重置索引
        df_new.reset_index(drop=True, inplace=True)
        
        # 选择并重命名列
        df_new = df_new[['股票名称', '股票代码', '日期', '开盘', '收盘', '最高', '最低', '成交量']]
        df_new.columns = ['stock_name', 'stock_code', 'trade_date', 'open', 'close', 'high', 'low', 'volume']
        
        # 统一股票代码格式（添加.SH后缀）
        df_new["stock_code"] = df_new["stock_code"].apply(lambda x: x + ".SH")
        
        # 如果是增量更新且已有文件存在，则合并数据
        if is_incremental and self.output_path.exists():
            try:
                logger.info("增量更新模式：合并新旧数据")
                df_old = pd.read_csv(self.output_path)
                
                # 合并新旧数据
                df_total = pd.concat([df_old, df_new], ignore_index=True)
                
                # 去重（基于stock_code和trade_date，保留最新的数据）
                df_total = df_total.drop_duplicates(
                    subset=['stock_code', 'trade_date'],
                    keep='last'
                ).reset_index(drop=True)
                
                # 按日期和股票代码排序
                df_total = df_total.sort_values(
                    by=['trade_date', 'stock_code']
                ).reset_index(drop=True)
                
                logger.info(f"合并后总记录数: {len(df_total)} (旧: {len(df_old)}, 新: {len(df_new)})")
            except Exception as e:
                logger.warning(f"合并数据失败: {e}，将只保存新数据")
                df_total = df_new
        else:
            df_total = df_new
        
        # 保存到CSV
        df_total.to_csv(self.output_path, index=False, encoding='utf-8')
        logger.info(f"数据已保存到: {self.output_path}")
        logger.info(f"总共 {len(df_total)} 条记录")
        
        return df_total
    
    def run(
        self,
        default_start_date: str = "20251001",
        auto_date_range: bool = True
    ) -> Optional[pd.DataFrame]:
        """执行完整的数据获取流程
        
        支持自动日期范围检测：
        - 如果已有数据文件，从最后日期的下一天开始获取
        - 如果没有数据文件，从default_start_date开始获取
        - 结束日期始终为今天
        
        Args:
            default_start_date: 默认开始日期，格式 'YYYYMMDD'（仅在没有已有数据时使用）
            auto_date_range: 是否自动检测日期范围，默认True
            
        Returns:
            整合后的DataFrame，如果无需更新则返回None
        """
        try:
            # 1. 加载股票列表
            stock_list = self.load_stock_list()
            
            # 2. 确定日期范围
            if auto_date_range:
                begin_date, end_date = self.get_date_range(default_start_date)
                
                # 检查是否需要更新
                if begin_date > end_date:
                    logger.info("数据已是最新，无需更新")
                    # 返回已有数据
                    if self.output_path.exists():
                        return pd.read_csv(self.output_path)
                    return None
                    
                is_incremental = self.output_path.exists()
            else:
                begin_date = default_start_date
                end_date = datetime.now().strftime("%Y%m%d")
                is_incremental = False
            
            # 3. 获取盘中数据
            logger.info(f"数据获取日期范围: {begin_date} - {end_date}")
            df_dict = self.fetch_intraday_data(stock_list, begin_date, end_date)
            
            # 4. 处理并保存数据
            df_total = self.process_and_save_data(df_dict, is_incremental)
            
            logger.info("数据获取流程完成")
            return df_total
            
        except Exception as e:
            logger.error(f"数据获取流程失败: {e}")
            raise


def main():
    """主函数
    
    执行A股盘中数据获取，支持增量更新：
    - 首次运行：从default_start_date开始获取所有数据
    - 后续运行：自动从上次最后日期的下一天开始获取
    """
    # 创建数据获取器实例
    fetcher = AStockIntradayDataFetcher(
        frequency=60,  # 60分钟K线
        stock_list_file="sse_50_weight.csv",  # 上证50权重文件
        output_file="A_stock_hourly.csv"
    )
    
    # 执行数据获取（自动检测日期范围）
    df = fetcher.run(
        default_start_date="20251001",  # 仅在首次运行时使用
        auto_date_range=True  # 启用自动日期范围检测
    )
    
    # 显示数据概览
    if df is not None and not df.empty:
        print("\n" + "="*50)
        print("数据概览:")
        print("="*50)
        print(df.head(10))
        print(f"\n数据形状: {df.shape}")
        print(f"股票数量: {df['stock_code'].nunique()}")
        print(f"日期范围: {df['trade_date'].min()} - {df['trade_date'].max()}")
    else:
        print("\n" + "="*50)
        print("无新数据或数据获取失败")
        print("="*50)


if __name__ == "__main__":
    main()

