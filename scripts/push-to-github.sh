#!/usr/bin/env bash
set -euo pipefail

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

printf "GitHub owner/user/org: "
read -r GH_OWNER
printf "Repository name: "
read -r GH_REPO
printf "Branch [main]: "
read -r BRANCH
BRANCH="${BRANCH:-main}"
printf "Git author name [Fap Instructor Personal]: "
read -r GIT_NAME
GIT_NAME="${GIT_NAME:-Fap Instructor Personal}"
printf "Git author email [actions@users.noreply.github.com]: "
read -r GIT_EMAIL
GIT_EMAIL="${GIT_EMAIL:-actions@users.noreply.github.com}"

cat <<'EOF'

Paste a GitHub token that has access to the target repository.
Required permissions:
  - Contents: Read and Write
  - Workflows: Read and Write
Classic token scopes, if using classic PAT:
  - repo
  - workflow

The token will not be stored in git config or the remote URL.
EOF
printf "GitHub token: "
# shellcheck disable=SC2162
read -rs GITHUB_TOKEN
printf "\n"

if [[ -z "${GH_OWNER}" || -z "${GH_REPO}" || -z "${GITHUB_TOKEN}" ]]; then
  echo "Owner, repo, and token are required." >&2
  exit 1
fi

if [[ ! -d .git ]]; then
  git init
fi

git config user.name "${GIT_NAME}"
git config user.email "${GIT_EMAIL}"
git branch -M "${BRANCH}"

git add .
if git diff --cached --quiet; then
  echo "No file changes to commit."
else
  git commit -m "Initial personal Docker app"
fi

REMOTE_URL="https://github.com/${GH_OWNER}/${GH_REPO}.git"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "${REMOTE_URL}"
else
  git remote add origin "${REMOTE_URL}"
fi

ASKPASS_FILE="$(mktemp)"
cat > "${ASKPASS_FILE}" <<'EOF'
#!/usr/bin/env sh
case "$1" in
  *Username*) printf '%s\n' 'x-access-token' ;;
  *Password*) printf '%s\n' "$GITHUB_TOKEN" ;;
  *) printf '\n' ;;
esac
EOF
chmod 700 "${ASKPASS_FILE}"
trap 'rm -f "${ASKPASS_FILE}"' EXIT

GIT_ASKPASS="${ASKPASS_FILE}" GITHUB_TOKEN="${GITHUB_TOKEN}" git push -u origin "${BRANCH}"

echo "Pushed to ${REMOTE_URL} on branch ${BRANCH}."
echo "Revoke or rotate the token if it was only created for this push."
