@echo off
echo Iniciando HQ Reader...
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale em https://python.org
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Criando ambiente virtual...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Instalando dependencias...
pip install -q -r requirements.txt

echo.
echo Servidor rodando em: http://localhost:5000
echo Acesse pelo iPad no mesmo Wi-Fi usando o IP do seu PC
echo Para encerrar: Ctrl+C
echo.
python app.py
pause
