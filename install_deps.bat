@echo off
chcp 65001 >nul
title 小说世界 - 安装依赖
cd /d H:\小说世界

echo 正在安装依赖...
pip install requests
pip install openpyxl
echo.
echo 依赖安装完成！
pause
