#! /bin/bash

sudo apt install -y git curl python3 python3-pip python3-venv
# The following test is needed in case VScode was installed by other
# means (e.g. using Ubuntu snap)
if ! which code; then
  wget -O code.deb https://go.microsoft.com/fwlink/?LinkID=760868
  sudo apt install -y ./code.deb
  rm code.deb
fi
code --install-extension jroesch.lean
wget https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh
bash elan-init.sh -y
rm elan-init.sh
python3 -m pip install --user pipx
python3 -m pipx ensurepath
. ~/.profile
pipx install mathlibtools
