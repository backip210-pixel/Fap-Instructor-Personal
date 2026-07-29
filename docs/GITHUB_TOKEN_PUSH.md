# Push to GitHub with a token

Yes — you can push this repository with a GitHub authentication token. This is often easier than uploading files from mobile, especially because GitHub workflows live under `.github/workflows` and token/API uploads need workflow permission.

## Recommended token type

Create a **fine-grained personal access token**:

1. GitHub → profile photo → **Settings**
2. **Developer settings**
3. **Personal access tokens** → **Fine-grained tokens**
4. **Generate new token**
5. Repository access: choose only your target repository
6. Permissions:
   - **Contents: Read and write**
   - **Workflows: Read and write**
   - Metadata is read-only by default
7. Set a short expiry, e.g. 1 day

If using a classic PAT instead, it needs:

- `repo`
- `workflow`

The `workflow` permission is important because this repo contains files in `.github/workflows/`.

## Safer way to use the token

Do **not** save the token in the git remote URL. Use the helper script:

```bash
cd fapinstructor-docker
./scripts/push-to-github.sh
```

The script will prompt for:

- GitHub username/org
- repository name
- branch, default `main`
- token

It uses a temporary `GIT_ASKPASS` helper and does not store the token in `.git/config`.

## If you must push manually

```bash
cd fapinstructor-docker
git init
git add .
git commit -m "Initial personal Docker app"
git branch -M main
git remote add origin https://github.com/YOUR-GITHUB-USER/YOUR-REPO.git

export GITHUB_TOKEN='paste-token-here'
cat >/tmp/git-askpass.sh <<'EOF'
#!/usr/bin/env sh
case "$1" in
  *Username*) echo "x-access-token" ;;
  *Password*) echo "$GITHUB_TOKEN" ;;
esac
EOF
chmod 700 /tmp/git-askpass.sh
GIT_ASKPASS=/tmp/git-askpass.sh git push -u origin main
rm -f /tmp/git-askpass.sh
unset GITHUB_TOKEN
```

## Why mobile uploads may not trigger workflows

Common causes:

- The workflow file was not uploaded to exactly `.github/workflows/*.yml`
- Actions are disabled for the repository
- The commit did not land on the default branch
- GitHub ignored/blocked workflow file creation because the token/session did not have workflow permission
- You uploaded a zip instead of extracted files

After the repo is pushed correctly, open the GitHub repository → **Actions** and enable workflows if GitHub prompts you to do so.
