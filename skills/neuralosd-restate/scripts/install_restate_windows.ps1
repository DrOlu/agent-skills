# =====================================================================
# neuralosd-restate on Windows - use WSL2 (official server binaries are
# macOS + Linux; there is no native Windows server build).
# Run this in an elevated PowerShell.
# =====================================================================

# 1. Install WSL2 + Ubuntu (reboot may be required)
wsl --install -d Ubuntu

# 2. Inside Ubuntu (wsl -d Ubuntu), run the standard Linux installer:
#    bash scripts/install_restate.sh
#
# 3. Keep the server running after WSL exits - either enable systemd
#    (in /etc/wsl.conf:  [boot]
#    systemd=true , then wsl --shutdown)
#    and install a systemd unit, or run under a persistent wsl session:
#
#    nohup ~/restate/restate-server-*/restate-server &
#
# 4. Optional: register a Windows service wrapper with NSSM so the WSL
#    server starts at boot:
#    nssm install RestateServer "C:\Windows\System32\wsl.exe" -d Ubuntu --exec /bin/bash -c "exec ~/restate/restate-server-*/restate-server"
#    nssm set RestateServer AppDirectory C:\wsl
#    nssm start RestateServer
#
# 5. Verify from Windows PowerShell:
#    curl.exe http://localhost:9070/health
#    curl.exe -X POST http://localhost:8080/WemaAsk/ask -d '"how many open incidents"'
#
# Ports 8080 (ingress) and 9070 (admin/UI) are forwarded from WSL2 to
# Windows automatically on localhost.
