#!/bin/bash

# helper: yes/no prompt
prompt_confirm() {
  local prompt="${1:-Are you sure?}" default="${2:-n}" ans
  if [[ "$default" =~ ^[Yy]$ ]]; then
    yn_prompt="[Y/n]"
  else
    yn_prompt="[y/N]"
  fi
  while true; do
    read -rp "$prompt $yn_prompt: " ans
    ans="${ans:-$default}"
    case "$ans" in
      [Yy]|[Yy][Ee][Ss]) return 0 ;;
      [Nn]|[Nn][Oo])     return 1 ;;
      *) echo "Please answer yes or no." ;;
    esac
  done
}