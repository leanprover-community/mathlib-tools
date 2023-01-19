#! /bin/bash

sudo apt install -y git curl python3 python3-pip python3-venv
# The following test is needed in case VScode or VSCodium was installed by other
# means (e.g. using Ubuntu snap)
vsc="$(which code || which codium)"
if [ -z "$vsc" ]; then
  wget -O code.deb https://go.microsoft.com/fwlink/?LinkID=760868
  sudo apt install -y ./code.deb
  rm code.deb
  vsc=code
fi
"$vsc" --install-extension jroesch.lean
wget https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh
bash elan-init.sh -y
rm elan-init.sh
python3 -m pip install --user pipx
python3 -m pipx ensurepath
. ~/.profile
pipx install mathlibtools
