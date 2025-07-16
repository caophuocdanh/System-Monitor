Get-Process | Where-Object { $_.ProcessName -like "*python*" } | Stop-Process -Force
Start-Process py -ArgumentList "server.py" -WindowStyle Minimized
Start-Process py -ArgumentList "dashboard.py" -WindowStyle Minimized
Start-Process py -ArgumentList "client.py" -WindowStyle Minimized