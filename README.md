# Customization-Scripts
Various scripts and documentation to help me customize my devices

# To get started....
Install Github cli (not required but hey, it's fun.)

# Official instructions are here on [Github's repo](https://github.com/cli/cli/blob/trunk/docs/install_linux.md)

# TL:DR;
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/etc/apt/trusted.gpg.d/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/trusted.gpg.d/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh

# Test
I made this change in a new branch, then merged to the dev branch, and am HOPING the Github action picks it up and merges to alpha and main. Here goes...
