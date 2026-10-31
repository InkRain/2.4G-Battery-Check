@echo off
chcp 65001 >nul
REM ============================================================
REM  2.4G Battery Check 一键打包脚本
REM  需要: Python 3.10+ ，先执行 pip install -r requirements.txt pyinstaller
REM ============================================================
cd /d %~dp0

echo [1/2] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] 开始打包（单文件）...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "2.4G Battery Check" ^
    --icon "app\resources\app.ico" ^
    --add-data "app\resources;app\resources" ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtWidgets ^
    main.py

if errorlevel 1 (
    echo.
    echo 打包失败！请检查上方错误信息。
    pause
    exit /b 1
)
echo.
echo 打包完成：dist\2.4G Battery Check.exe（单文件，约 40MB）
pause
