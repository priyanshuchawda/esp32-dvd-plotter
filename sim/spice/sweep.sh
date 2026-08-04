#!/usr/bin/env bash
# Sweep step rate and report how much coil current, and therefore torque,
# actually develops. Usage: sim/spice/sweep.sh [rates...]
set -euo pipefail

deck="$(dirname "$0")/coil.cir"
rates=("${@:-}")
[ -z "${rates[0]}" ] && rates=(200 500 1000 2000 3000 4000 6000 8000)

printf '%10s  %10s  %8s\n' 'steps/s' 'peak (mA)' 'torque'
for f in "${rates[@]}"; do
    tmp=$(mktemp /tmp/coil_XXXX.cir)
    sed "s/^\.param fstep=.*/.param fstep=$f/" "$deck" > "$tmp"
    # ngspice writes .meas results to stderr, so keep it.
    res=$(ngspice -b "$tmp" 2>&1 || true)
    rm -f "$tmp"
    # awk, not bc: ngspice prints scientific notation and bc cannot parse it.
    awk -v f="$f" '
        /tran1.ipeak/ { pk = $3 }
        /tran1.frac/  { fr = $3 }
        END { printf "%10s  %10.1f  %7.0f%%\n", f, pk * 1000, fr * 100 }
    ' <<<"$res"
done
