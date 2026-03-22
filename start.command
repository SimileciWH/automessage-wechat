#!/bin/bash
cd "$(dirname "$0")"
nohup python app.py > logs/app.log 2>&1 &
sleep 1
open http://localhost:5001
