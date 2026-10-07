#!/usr/bin/env bash
# Messages in several languages for the Linux scripts (install-linux.sh, update.sh). Source this file:
#
#   source "$(dirname "$0")/lib/i18n.sh"
#   i18n_init install-linux            # loads lang/install-linux.<language>.msg, English is the fallback
#   echo "$(t step_done "$HOST" 8443)" # {0}, {1} ... in the text are replaced by the arguments
#
# Language: FAMULUS_LANG=de|en|ru (set by the language scripts install-linux.de.sh etc. or --lang),
# otherwise from the system locale (LC_ALL, LC_MESSAGES, LANG), English if there is no translation.
#
# Catalog format - the same as for the Windows scripts: one text per line, key = 'text'
# ('' stands for a quote, lines starting with # are comments).

# bash 5.2 treats "&" in the replacement text of ${var//a/b} specially - arguments may contain one
shopt -u patsub_replacement 2>/dev/null || true

declare -A MSG FALLBACK_MSG

i18n_language() {   # prints de, en or ru
  case "${FAMULUS_LANG:-}" in de|en|ru) echo "$FAMULUS_LANG"; return ;; esac
  case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
    de*) echo de ;;
    ru*) echo ru ;;
    *) echo en ;;
  esac
}

i18n_load() {   # i18n_load <file> <array name>
  local file="$1" line key text sq="'"
  local -n target="$2"
  [ -f "$file" ] || return 0
  local re="^[[:space:]]*([A-Za-z0-9_]+)[[:space:]]*=[[:space:]]*'(.*)'[[:space:]]*\$"
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"                 # files may have Windows line endings ...
    line="${line#$'\xef\xbb\xbf'}"       # ... and a byte order mark
    if [[ $line =~ $re ]]; then
      key="${BASH_REMATCH[1]}"
      text="${BASH_REMATCH[2]}"
      target["$key"]="${text//$sq$sq/$sq}"
    fi
  done < "$file"
}

i18n_init() {   # i18n_init <catalog name>
  local dir language
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lang" && pwd)"
  language="$(i18n_language)"
  i18n_load "$dir/$1.en.msg" FALLBACK_MSG
  [ "$language" = en ] || i18n_load "$dir/$1.$language.msg" MSG
}

t() {   # t <key> [argument ...]  -> text with {0} {1} ... filled in (the key itself if it is unknown)
  local key="$1"; shift
  local text="${MSG[$key]-${FALLBACK_MSG[$key]-$key}}" i=0 arg
  for arg in "$@"; do
    text="${text//\{$i\}/$arg}"
    i=$((i + 1))
  done
  printf '%s' "$text"
}
