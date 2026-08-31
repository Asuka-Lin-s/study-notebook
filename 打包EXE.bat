@echo off
chcp 65001 >nul
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "学习笔记" app.py
echo.
echo 打包完成：dist\学习笔记.exe
pause
