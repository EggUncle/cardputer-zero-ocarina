#!/bin/bash
# Run from the root-owned installation. Drop-in is removed on exit.
set -euo pipefail
owner=${1:?pass numeric player uid}
[[ $EUID == 0 && $owner =~ ^[0-9]+$ ]]
base=/opt/cardputer-ocarina
drop=/run/systemd/system/bluetooth.service.d/80-ocarina-session.conf
[[ -x $base/pcble2gamepad-controller-backend && ! -e $drop ]]
systemctl is-active --quiet bluetooth
[[ -z "$(bluetoothctl devices Connected)" ]] || { echo '请先断开其他蓝牙设备'; exit 1; }
mkdir -p "${drop%/*}"
cleanup() {
    rm -f "$drop"
    systemctl daemon-reload
    systemctl restart bluetooth
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
cat > "$drop" <<'UNIT'
[Service]
ExecStart=
ExecStart=/usr/libexec/bluetooth/bluetoothd --compat --noplugin=*
UNIT
systemctl daemon-reload
systemctl restart bluetooth
args=()
if [[ ${2:-} == auto ]]; then
    # The backend stores authenticated peers under the adapter and peer addresses.
    adapter=$(bluetoothctl list | awk '/^Controller / {print $2; exit}')
    records=(/var/lib/pcble2gamepad/pairings/"$owner"/"${adapter//:/_}"__*.ini)
    if [[ ${#records[@]} == 1 && -f ${records[0]} ]]; then
        peer=${records[0]##*__}
        peer=${peer%.ini}
        [[ $peer =~ ^([[:xdigit:]]{2}_){5}[[:xdigit:]]{2}$ ]] && args=(--reconnect "${peer//_/:}")
    fi
fi
"$base/pcble2gamepad-controller-backend" hci0 "$base/pro-controller.xml" --desktop "$owner" --type pro "${args[@]}"
