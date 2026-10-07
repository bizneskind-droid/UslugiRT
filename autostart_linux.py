import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def linux_task(selected_time):

    working_dir = Path.cwd()
    
    now = datetime.now()
    target = datetime.combine(
        now.date(),
        datetime.strptime(selected_time, "%H:%M").time(),
    )

    if target <= now:
        target += timedelta(days=1)

    target -= timedelta(seconds=15)
    calendar_time = target.strftime("%Y-%m-%d %H:%M:%S")
    
    subprocess.run(
    [
        "systemd-run",
        "--user",
        f"--unit=uslugirt-{selected_time.replace(':', '-')}",
        f"--on-calendar={calendar_time}",
        "--timer-property=WakeSystem=true",
        "--timer-property=AccuracySec=1us",
        
        "--property=ExecStartPre=/usr/bin/nm-online -q -t 30",
        
        f"--working-directory={working_dir}",
        f"{working_dir}/.venv/bin/python",
        f"{working_dir}/main.py",
        "--time",
        selected_time,
    ],
    check=True,
    )

