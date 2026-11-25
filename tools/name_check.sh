#!/usr/bin/env bash
# Check whether candidate brand domains are registered, using whois only (see naming.md).
#
#   tools/name_check.sh                 # check every domain in DOMAINS below
#   tools/name_check.sh foo.com bar.org # check just these
#
# Prints "<domain>  TAKEN" or "<domain>  AVAILABLE". When whois gives no answer it can read
# (timeout, rate limit, an unfamiliar format) it prints UNKNOWN rather than guess.
# AVAILABLE means only "not registered": it says nothing about premium pricing, registry
# reservations or trademarks. TAKEN includes parked domains that may be for sale.

set -u

DOMAINS=(
  # Shortlist (fighter and advocate, stands alone)
  careback.com
  careback.org
  getcareback.com
  carebackhealth.com
  openclaim.com
  openclaim.org
  openclaimhealth.com
  fairshake.com
  fairshake.org
  fairshakehealth.com
  getfairshake.com

  # Other current candidates
  duecare.com
  duecare.org
  duecarehealth.com
  pushback.com
  pushbackhealth.com
  openadvocate.com
  openadvocate.org
  backstophealth.com
  backstopcare.com
  squaredealhealth.com
  squaredealcare.com
  carecounter.com
  carecounter.org
  countercharge.com

  # "Care" and "Health" combinations from the guidance
  careadvocate.org
  opencareadvocate.com
  healthpushback.com
  fairhealthbill.com
  mycareback.com

  # First-round names, for comparison
  plumbhealth.com
  trueuphealth.com
  secondlookhealth.com
  recounthealth.com
  itemizedhealth.com
  candorhealth.com
  fairsharehealth.com
  openbill.org
  openeob.com
  openeob.org
)

TIMEOUT=30   # seconds per query
PAUSE=1      # seconds between queries, to stay under registry rate limits

with_timeout() {
  # macOS whois has no timeout option; perl's alarm gives it one.
  perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" "$@"
}

registry_for() {
  # Ask IANA once per TLD for the registry's whois server, caching it in REG_<tld> and
  # setting SERVER. Asking the registry directly is enough to tell registered from not, and
  # skips the registrar's own server, which plain `whois` follows and which often times out.
  # Called without $(...) so the cache survives between domains.
  local var="REG_${1//[^a-z0-9]/_}"
  if [ -z "${!var:-}" ]; then
    printf -v "$var" '%s' "$(with_timeout whois -h whois.iana.org "$1" 2>/dev/null | awk '/^whois:/ {print $2; exit}')"
  fi
  SERVER=${!var}
}

check() {
  local domain=$1 out server
  registry_for "${domain##*.}"
  server=$SERVER
  if [ -n "$server" ]; then
    out=$(with_timeout whois -h "$server" "$domain" 2>&1) || true
  else
    out=$(with_timeout whois "$domain" 2>&1) || true
  fi
  local lower
  lower=$(printf '%s' "$out" | tr '[:upper:]' '[:lower:]' | tr -d '\r')

  if printf '%s' "$lower" | grep -qE 'no match for|domain not found|^not found|no data found|status: *free|no entries found'; then
    RESULT=AVAILABLE
  elif printf '%s' "$lower" | grep -qE "domain name: *${domain}\$"; then
    RESULT=TAKEN
  else
    RESULT=UNKNOWN
  fi
}

if [ $# -gt 0 ]; then
  DOMAINS=("$@")
fi

for domain in "${DOMAINS[@]}"; do
  domain=$(printf '%s' "$domain" | tr '[:upper:]' '[:lower:]')
  check "$domain"
  printf "%-26s %s\n" "$domain" "$RESULT"
  sleep "$PAUSE"
done
