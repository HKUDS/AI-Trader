#!/usr/bin/env python3
"""
合并100支美股科技股数据为系统所需的 merged.jsonl 格式
"""
import json
import glob
from pathlib import Path

def merge_stock_data():
    """将所有 daily_prices_*.json 文件合并为 merged.jsonl"""
    
    # 数据目录
    data_dir = Path(__file__).parent
    output_file = data_dir / "merged.jsonl"
    
    # 查找所有价格数据文件
    json_files = glob.glob(str(data_dir / "daily_prices_*.json"))
    
    if not json_files:
        print("❌ 未找到任何 daily_prices_*.json 文件")
        return
    
    print(f"📊 找到 {len(json_files)} 个股票数据文件")
    
    # 写入 JSONL 文件
    with open(output_file, 'w', encoding='utf-8') as outf:
        for json_file in sorted(json_files):
            try:
                with open(json_file, 'r', encoding='utf-8') as inf:
                    data = json.load(inf)
                    
                    # 写入一行（JSONL 格式）
                    outf.write(json.dumps(data, ensure_ascii=False) + '\n')
                    
                    symbol = data.get('Meta Data', {}).get('2. Symbol', 'Unknown')
                    print(f"✅ 已处理: {symbol}")
                    
            except Exception as e:
                print(f"❌ 处理文件 {json_file} 时出错: {e}")
    
    print(f"\n🎉 数据合并完成！")
    print(f"📁 输出文件: {output_file}")
    print(f"📊 共处理 {len(json_files)} 支股票")

if __name__ == "__main__":
    merge_stock_data()
