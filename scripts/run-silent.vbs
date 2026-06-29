Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File """ & _
    "C:\Users\Vineet.Saxena\Desktop\Fifa_World_Cup_2026\scripts\refresh.ps1""", 0, False
