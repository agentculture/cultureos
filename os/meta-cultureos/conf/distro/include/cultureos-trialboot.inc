# CultureOS rollback, kernel side (decision c39, task t15, docs/os/rollback.md).
#
# Reboot CULTUREOS_PANIC_TIMEOUT seconds after a kernel panic instead of
# hanging (the kernel is built with CONFIG_PANIC_TIMEOUT=0). After the reset
# the one-shot trial entry is gone and the firmware boots the unchanged
# default deployment.
#
# meta-updater writes OSTREE_KERNEL_ARGS (sota_qcom.bbclass default: console,
# root=LABEL=otaroot, KERNEL_CMDLINE_EXTRA) into the `options` line of the
# OSTree BLS entry; the UKI carries no command line of its own (UKI_CMDLINE =
# ""), so systemd-stub passes these options to the kernel. Later deployments
# inherit them, and cultureos-trialboot re-applies panic= to every trial.
#
# Pulled in by `require conf/distro/include/cultureos-trialboot.inc` in
# conf/distro/cultureos.conf (added by the image integration task, t19).
CULTUREOS_PANIC_TIMEOUT ?= "5"
OSTREE_KERNEL_ARGS:append = " panic=${CULTUREOS_PANIC_TIMEOUT}"
