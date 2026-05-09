# Versioning

Version is stored in `VERSION` (plain text, one line: `0.1.0`).  
It is read at app startup and shown in the footer of every page.

## How to bump

```bash
# 1. Edit VERSION
echo "0.2.0" > VERSION

# 2. Commit and tag
git add VERSION
git commit -m "Bump to v0.2.0"
git tag v0.2.0

# 3. Push both the commit and the tag
git push && git push --tags
```

GitHub shows tags under **Releases / Tags**.  
The footer updates on the next container restart — no rebuild needed.

## When to bump

| Change | Version part | Example |
|---|---|---|
| Bug fix | PATCH | 0.1.0 → 0.1.1 |
| New feature | MINOR | 0.1.1 → 0.2.0 |
| Breaking change | MAJOR | 0.2.0 → 1.0.0 |
