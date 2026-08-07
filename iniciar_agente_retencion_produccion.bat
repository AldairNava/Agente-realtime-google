@echo off
title Agente Retencion - Produccion
cd /d "%~dp0"
echo Iniciando agente de voz Retencion en modo Produccion (Conectado a SIP y Vicidial)...

powershell -Command "py -3.12 main.py --campania retencion --mode produccion --server 1"

pause
