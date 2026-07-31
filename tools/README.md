# Project-local ngspice

This workspace uses a portable Windows x64 installation of ngspice 46:

```text
tools/ngspice/bin/ngspice_con.exe
```

Source package:

```text
https://sourceforge.net/projects/ngspice/files/ng-spice-rework/46/ngspice-46_64.7z/download
```

The downloaded archive was verified before extraction:

```text
MD5 86d3d4f501a345e0f92945689a355fa9
```

The extracted binary directory and downloaded archives are intentionally
ignored by Git. CircuitPilot automatically searches this location when a
system-wide `ngspice` command is unavailable.
