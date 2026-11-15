@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe
set NAME=爽哥MD编辑工具
set SRC=爽哥MD命令生成工具.py

echo [1/4] 检查 Python 与 PyInstaller...
"%PY%" -c "import PyInstaller, sys; print('PyInstaller', PyInstaller.__version__, 'on', sys.version.split()[0])"
if errorlevel 1 goto :fail

echo [2/4] 检查资源文件...
for %%f in (app.ico md_file.ico app_icon.png md_file_icon.png version_info.txt "%SRC%") do (
    if not exist "%%~f" (
        echo 缺少文件：%%~f
        goto :fail
    )
)

echo [3/4] 打包...
"%PY%" -m PyInstaller --noconfirm --onefile --noconsole --name "%NAME%" --icon "app.ico" --add-data "app.ico;." --add-data "md_file.ico;." --add-data "app_icon.png;." --add-data "md_file_icon.png;." --version-file "version_info.txt" "%SRC%"
if errorlevel 1 goto :fail

echo [4/4] 清理中间产物...
if exist build rmdir /s /q build
if exist __pycache__ rmdir /s /q __pycache__
if exist "%NAME%.spec" del /q "%NAME%.spec"
if exist dist rmdir /s /q dist

echo.
echo 打包完成：%NAME%.exe
echo 提示：图标资源已内嵌；文件关联图标会自动复制到 %%LOCALAPPDATA%%\%NAME%%\icons 保持长期有效。
goto :eof

:fail
echo 打包失败，请查看上方错误输出。
exit /b 1
