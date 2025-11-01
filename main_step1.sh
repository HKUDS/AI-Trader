#!/bin/bash

# prepare data

cd ./data
# python get_daily_price.py #run daily price data
python get_interdaily_price.py #run interdaily price data
python merge_jsonl.py
cd ../
