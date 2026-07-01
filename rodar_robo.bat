@echo off
cd /d "%~dp0"
set PY=C:\Users\Andres\AppData\Local\Programs\Python\Python311\python.exe

echo Instalando browser do Playwright...
%PY% -m playwright install chromium

echo.
echo Iniciando extracao de dados w1nner...
%PY% robo.py

echo.
if %ERRORLEVEL% == 0 (
    echo Sucesso! Fazendo push para o GitHub...
    git add dados_extraidos.csv ranking_muapd.csv ranking_7dias.csv ranking_muepd.csv top10_ap.csv metas.json
    git commit -m "dados: atualizacao manual"
    git pull --rebase --autostash origin main
    git push
    echo Dashboard atualizado!
) else (
    echo Erro na extracao. Verifique as mensagens acima.
)
pause
