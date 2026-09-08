@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Gerar EXE - GP-H Central v0.35.0

echo ==========================================
echo   GP-H CENTRAL - BUILD WINDOWS v0.35.0
echo ==========================================
echo.

where py >nul 2>nul
if errorlevel 1 goto :NOPYY

py -3 -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo PyInstaller ainda nao esta instalado.
    echo Para instalar: py -3 -m pip install pyinstaller
    pause
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [1/2] Gerando GP-H_Updater.exe sem console...
py -3 -m PyInstaller --clean --noconfirm "GP-H_Updater.spec"
if errorlevel 1 goto :FAIL

echo [2/2] Gerando GP-H Central Historica.exe sem console...
py -3 -m PyInstaller --clean --noconfirm "GP-H_Central.spec"
if errorlevel 1 goto :FAIL

if not exist "dist\GP-H_Updater.exe" goto :FAIL
if not exist "dist\GP-H Central Historica.exe" goto :FAIL

echo.
echo Concluido.
echo A distribuicao Windows precisa manter lado a lado:
echo   - GP-H Central Historica.exe
echo   - GP-H_Updater.exe
echo.
echo Os dados continuam em %%LOCALAPPDATA%%\GP-H_Central_Historica\dados
pause
exit /b 0

:FAIL
echo.
echo FALHA AO GERAR A DISTRIBUICAO.
pause
exit /b 1

:NOPYY
echo Python launcher ^(py^) nao encontrado.
pause
exit /b 1
