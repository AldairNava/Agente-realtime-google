@echo off
title Agente Retencion - Local
cd /d "%~dp0"
echo Iniciando agente de voz Retencion en modo Local...

powershell -Command "py -3.12 main.py --campania retencion --mode local"

pause
