@echo off
title Agente Plata - Pruebas
cd /d "%~dp0"
echo Iniciando agente de voz Plata en modo Pruebas con usuario "plata"...

powershell -Command "py -3.12 main.py --campania plata --user 'plata 5' --mode pruebas"

pause