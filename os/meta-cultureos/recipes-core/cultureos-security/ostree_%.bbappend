# CultureOS: give ostree an ed25519 signature engine (cultureos-security, plan
# task t12).
#
# meta-oe builds ostree with glib crypto only, and meta-updater removes gpgme,
# so the stock target ostree has no signature support at all and cannot honor
# sign-verify=true in /etc/ostree/remotes.d/. libsodium provides ed25519
# (`ostree --version` then lists "sign-ed25519"). This applies to the native
# ostree too, which the release pipeline (t17) needs for `ostree sign`.
#
# This bbappend lives in the cultureos-security recipe dir on purpose: the
# layer's BBFILES matches recipes-*/*/*.bbappend, and keeping it here keeps
# the hardening in one place.
PACKAGECONFIG:append = " ed25519-libsodium"
