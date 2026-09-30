"""Windows-style time zone choices and local storage preferences."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from PySide6.QtCore import QTimeZone

def time_zone_choices(current="Asia/Riyadh"):
    rows=[]
    try:
        import winreg, struct
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Time Zones") as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                name=winreg.EnumKey(root,i)
                with winreg.OpenKey(root,name) as key:
                    zone=bytes(QTimeZone.windowsIdToDefaultIanaId(name.encode())).decode()
                    if not zone:continue
                    try:ZoneInfo(zone)
                    except ZoneInfoNotFoundError:continue
                    label=winreg.QueryValueEx(key,"Display")[0]
                    bias=struct.unpack("<l",winreg.QueryValueEx(key,"TZI")[0][:4])[0]
                    rows.append((-bias,label,zone))
    except (ImportError,OSError):pass
    if not rows:rows=[(0,"(UTC) Coordinated Universal Time","UTC")]
    rows.sort(key=lambda row:(row[0],row[1]))
    choices=[(label,zone) for _,label,zone in rows]
    if current not in {zone for _,zone in choices}:choices.append((current,current))
    return choices
