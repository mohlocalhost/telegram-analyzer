#!/usr/bin/env bash
cd /home/moh/telegram_analyzer
python3 dashboard.py
python3 server.py &
sleep 0.8
termux-open-url "http://127.0.0.1:8080/dashboard.html"
echo "Server PID: $!"
echo "Stop with: kill $!"
